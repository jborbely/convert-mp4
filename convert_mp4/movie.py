import os
import re
import subprocess
import tempfile

from msl.io import search


class Movie(object):

    def __init__(self, path):
        super(Movie, self).__init__()
        self.path = path
        self.directory, self.title = os.path.split(path)
        self.subtitle = {}
        self.english_regex = re.compile('eng', flags=re.IGNORECASE)

        self.subtitles = self.get_subtitles()
        self.duration = self.get_duration()
        self.codec_info = self.get_codec_info()

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
            _, language = line.split(',')
            if self.english_regex.search(language):
                subs[f'English[{index}]'] = {'index': index, 'path': None}

        name, _ = os.path.splitext(self.title)
        for srt in search(self.directory, pattern=r'\.srt$', levels=None):
            if name not in srt:
                continue
            title = os.path.basename(srt)
            srt_name, _ = os.path.splitext(title)
            if srt_name == name or self.english_regex.search(title):
                subs[title] = {'index': None, 'path': srt}

        return dict(sorted(subs.items()))

    def get_duration(self) -> float:
        command = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'csv=p=0', self.path
        ]
        return float(subprocess.check_output(command))

    def get_codec_info(self) -> dict:
        # return example, {'video': 'h264', 'audio': 'aac'}
        info = {}
        for name in ('video', 'audio'):
            cmd = [
                'ffprobe', '-v', 'error', '-select_streams', name[0],
                '-show_entries', 'stream=codec_name',
                '-of', 'csv=p=0', self.path
            ]
            out = subprocess.check_output(cmd)
            info[name] = out.rstrip().decode()
        return info

    def load_subtitle(self, path_or_index: str | int) -> list[str]:
        """Load subtitles from an external file (str) or an internal stream (int)."""
        if isinstance(path_or_index, str):
            with open(path_or_index, encoding='utf-8', errors='replace') as fp:
                lines = fp.readlines()
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
