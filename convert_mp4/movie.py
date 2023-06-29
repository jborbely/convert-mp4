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
            '-show_entries', 'stream=index:stream_tags=language',
            '-of', 'csv=p=0', self.path
        ]
        out = subprocess.check_output(subtitles_cmd)

        subs = {}
        for index, line in enumerate(out.decode().splitlines()):
            if self.english_regex.search(line):
                subs[f'English[{index}]'] = {'index': index, 'path': None}

        name, _ = os.path.splitext(self.title)
        for srt in search(self.directory, pattern=r'\.(srt|idx)$', levels=None):
            if name not in srt:
                continue
            title = os.path.basename(srt)
            srt_name, _ = os.path.splitext(title)
            if srt_name == name or self.english_regex.search(title):
                subs[title] = {'index': None, 'path': srt}

        return dict(sorted(subs.items()))

    def load_subtitle(self, path_or_index: str | int) -> list[str]:
        """Load subtitles from an external file (str) or an internal stream (int)."""
        if isinstance(path_or_index, str):
            if path_or_index.endswith('.srt'):
                with open(path_or_index, encoding='utf-8', errors='replace') as fp:
                    lines = fp.readlines()
            else:
                lines = ['Picture-based IDX/SUB']
        else:
            outfile = os.path.join(tempfile.gettempdir(), f'{self.title}_{path_or_index}.srt')
            cmd = [
                'ffmpeg', '-i', self.path, '-c', 'copy',
                '-map', f'0:s:{path_or_index}', outfile
            ]
            subprocess.run(cmd, stderr=subprocess.PIPE)
            with open(outfile) as fp:
                lines = fp.readlines()
            os.remove(outfile)
        return lines
