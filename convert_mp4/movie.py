import os
import re
import subprocess

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
            '-show_entries', 'stream=index:stream_tags=language,title',
            '-of', 'csv=p=0', self.path
        ]
        out = subprocess.check_output(subtitles_cmd)

        subs = {}
        for index, line in enumerate(out.decode().splitlines()):
            items = line.split(',')
            if len(items) == 1 or not self.english_regex.search(items[1]):
                continue
            subs[f'{items[2]}[{index}:{items[0]}]'] = {'index': index, 'path': None}

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
