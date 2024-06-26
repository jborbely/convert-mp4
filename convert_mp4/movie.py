import json
import os
import re
import subprocess
import tempfile

from msl.io import search


class Movie:

    english_regex = re.compile(r'eng', flags=re.IGNORECASE)

    def __init__(self, path):
        super(Movie, self).__init__()
        self.path = path
        self.directory, self.title = os.path.split(path)
        self.subtitle = {}

        self.subtitles = self.get_subtitles()

        cmd = ['ffprobe', '-v', 'error', '-of', 'json',
               '-show_entries', 'stream:format', self.path]
        self.metadata = json.loads(subprocess.check_output(cmd))

        self.duration = float(self.metadata['format']['duration'])

        self.width = -1
        self.height = -1
        self.codec = {}
        for stream in self.metadata['streams']:
            self.codec[stream['codec_type']] = stream['codec_name']
            if self.width == -1 and 'width' in stream:
                self.width = int(stream['width'])
            if self.height == -1 and 'height' in stream:
                self.height = int(stream['height'])

        self.convert_path = None  # updated by ConvertMovieWorker

    def __repr__(self):
        return f'Movie<{self.title}>'

    def get_subtitles(self) -> dict:
        subtitles_cmd = [
            'ffprobe', '-v', 'error', '-select_streams', 's',
            '-show_entries', 'stream=index:stream=codec_name:stream_tags=language',
            '-of', 'csv=p=0', self.path
        ]
        out = subprocess.check_output(subtitles_cmd)

        subs = {}
        for index, line in enumerate(out.decode().splitlines()):
            split = line.split(',')
            codec, lang = '', ''
            if len(split) == 3:
                _, codec, lang = split
            elif len(split) == 2:
                _, codec = split

            if self.english_regex.search(lang):
                subs[f'English[{index}]'] = {'index': index, 'codec': codec, 'path': None}

        name, _ = os.path.splitext(self.title)
        for srt in search(self.directory, pattern=r'\.(srt|idx|ass)$', levels=None):
            if name not in srt:
                continue
            title = os.path.basename(srt)
            srt_name, _ = os.path.splitext(title)
            if srt_name == name or self.english_regex.search(title):
                subs[title] = {'index': None, 'codec': None, 'path': srt}

        return dict(sorted(subs.items()))

    def load_subtitle(self, info: dict) -> list[str]:
        """Load subtitles from an external file or an internal stream."""
        if info['path']:  # external file
            ext = os.path.splitext(info['path'])[1].lower()
            if ext == '.srt':
                with open(info['path'], encoding='utf-8', errors='replace') as f:
                    return f.readlines()
            elif ext == '.ass':
                # convert to srt format
                name, _ = os.path.splitext(os.path.basename(info['path']))
                outfile = os.path.join(tempfile.gettempdir(), f'{name}.srt')
                subprocess.run(['ffmpeg', '-i', info['path'], '-c:s', 'srt', outfile], stderr=subprocess.PIPE)
                with open(outfile, encoding='utf-8', errors='replace') as f:
                    lines = f.readlines()
                os.remove(outfile)
                return lines
            elif ext == '.idx':
                return ['Picture-based IDX/SUB']
            else:
                raise ValueError(f'Unhandled subtitle extension {ext}')

        # internal stream
        if info['codec'] == 'subrip':
            ext = 'srt'
        elif info['codec'] == 'ass':
            ext = 'ass'
        else:
            raise ValueError(f'Unhandled subtitle codec {info["codec"]}')

        outfile = os.path.join(tempfile.gettempdir(), f'{self.title}.{ext}')
        cmd = ['ffmpeg', '-i', self.path, '-c', 'copy',
               '-map', f'0:s:{info["index"]}', outfile]

        if os.path.exists(outfile):
            os.remove(outfile)

        subprocess.run(cmd, stderr=subprocess.PIPE)
        with open(outfile, encoding='utf-8') as fp:
            lines = fp.readlines()
        os.remove(outfile)

        return lines
