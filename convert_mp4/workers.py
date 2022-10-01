import os
import re
import subprocess

from msl.qt import (
    QtCore,
    Signal
)

from .movie import Movie


class ConvertMovieSignaler(QtCore.QObject):
    percentage = Signal(int)
    error = Signal(str)


class ConvertMovieWorker(QtCore.QRunnable):

    def __init__(self, movie, event_stop):
        super(ConvertMovieWorker, self).__init__()
        self.movie = movie
        self.output_extension = '.mp4'
        self.signaler = ConvertMovieSignaler()
        self.regex_timestamp = re.compile(r'time=(?P<timestamp>\S+)')
        self.event_stop = event_stop

    @staticmethod
    def to_seconds(timestamp) -> float:
        split = timestamp.split(':')
        seconds = float(split[0]) * 60 * 60
        seconds += float(split[1]) * 60
        seconds += float(split[2])
        return seconds

    def run(self):
        root, ext = os.path.splitext(self.movie.path)
        if ext == self.output_extension:
            outfile = root + '_(copy)' + self.output_extension
        else:
            outfile = root + self.output_extension

        if os.path.isfile(outfile):
            print(f'{outfile} -- already exists')
            self.signaler.percentage.emit(0)
            self.signaler.error.emit('already exists')
            return

        basename = os.path.basename(self.movie.path)
        cmd = ['ffmpeg', '-i', basename]

        if self.movie.codec_info['audio'] == 'mp3':
            cmd.extend(['-acodec', 'aac'])
        else:
            cmd.extend(['-acodec', 'copy'])

        video_filters = []
        if self.movie.codec_info['video'] == 'hevc':
            cmd.extend(['-vcodec', 'libx264'])
            video_filters.append('format=yuv420p')

        if self.movie.subtitle:
            index = self.movie.subtitle['index']
            if index is not None:
                subs = f'{basename!r}:stream_index={index}'
            else:
                dirname = os.path.dirname(self.movie.path)
                subs = self.movie.subtitle['path'][len(dirname)+1:]
                subs = subs.replace('[', '\\[').replace(']', '\\]')
            video_filters.append(f'subtitles={subs}')

        if video_filters:
            cmd.extend(['-vf', ', '.join(video_filters)])
        else:
            cmd.extend(['-vcodec', 'copy'])

        cmd.append(os.path.basename(outfile))

        p = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=os.path.dirname(self.movie.path))

        for line in p.stdout:
            if self.event_stop.is_set():
                p.terminate()
                return

            if line.startswith('Conversion failed!') or \
                    line.endswith('cannot be used together.\n'):
                print(f'{outfile} -- ERROR: {line}')
                self.signaler.percentage.emit(0)
                self.signaler.error.emit(f'ERROR: {line}')
                os.remove(outfile)
                return

            match = self.regex_timestamp.search(line)
            if match:
                seconds = self.to_seconds(match['timestamp'])
                percentage = 100. * seconds / self.movie.duration
                self.signaler.percentage.emit(int(percentage))

        self.signaler.percentage.emit(100)


class LoadMovieSignaler(QtCore.QObject):
    finished = Signal(object)


class LoadMovieWorker(QtCore.QRunnable):

    def __init__(self, path):
        super(LoadMovieWorker, self).__init__()
        self.path = path
        self.signaler = LoadMovieSignaler()
        self.finished = self.signaler.finished

    def run(self):
        self.finished.emit(Movie(self.path))
