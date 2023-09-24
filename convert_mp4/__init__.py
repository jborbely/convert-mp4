import os
import re
import subprocess
import sys
import threading
import time
from functools import partial
from typing import cast

from msl.io import search
from msl.qt import Button
from msl.qt import Qt
from msl.qt import QtCore
from msl.qt import QtWidgets
from msl.qt import application
from msl.qt import prompt
from msl.qt.convert import to_qicon
from msl.qt.utils import drag_drop_paths
from msl.qt.utils import screen_geometry

from .workers import ConvertMovieWorker
from .workers import LoadMovieWorker
from .workers import LoadSubtitleWorker

__version__ = '0.1.0.dev0'


class TableDelegate(QtWidgets.QItemDelegate):

    def __init__(self, parent):
        """Allows for a QTableWidgetItem to be selectable while also in read-only mode."""
        super(TableDelegate, self).__init__(parent=parent)

    def createEditor(self, parent, option, index):
        editor = QtWidgets.QLineEdit(parent=parent)
        editor.setFrame(False)
        editor.setReadOnly(True)
        return editor


class VideoConverter(QtWidgets.QMainWindow):

    def __init__(self, config):
        super(VideoConverter, self).__init__()
        self.config = config
        self.load_pool = QtCore.QThreadPool()
        self.convert_pool = QtCore.QThreadPool()
        self.convert_pool.setMaxThreadCount(1)
        self.subtitle_pool = QtCore.QThreadPool()
        self.mutex = QtCore.QMutex()
        self.movies = {}
        self.paths = []
        self.subtitle_workers: list[LoadSubtitleWorker] = []
        self.extensions = config.get('extensions', ['avi', 'mkv', 'mp4'])
        self.extensions_regex = re.compile(r'\.({})$'.format('|'.join(self.extensions)))

        self.event_stop = threading.Event()

        self.setAcceptDrops(True)

        open_button = Button(
            left_click=self.open_folder,
            icon=QtWidgets.QStyle.SP_DialogOpenButton,
            tooltip='Open all videos in a folder (and sub-folders)'
        )
        open_button.add_menu_item(
            text='Open a video file',
            triggered=self.open_filename
        )

        convert_button = Button(
            left_click=self.convert,
            icon=icon('convert.png'),
            tooltip='Start converting'
        )

        abort_button = Button(
            left_click=self.abort,
            icon=icon('abort.png'),
            tooltip='Abort conversions'
        )

        self.toolbar = QtWidgets.QToolBar()
        self.toolbar.addWidget(open_button)
        self.toolbar.addWidget(convert_button)
        self.toolbar.addWidget(abort_button)
        self.addToolBar(self.toolbar)

        # disable being able to right-click on the toolbar and close it
        self.setContextMenuPolicy(Qt.NoContextMenu)

        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['Title', 'Subtitles', 'Status'])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSortIndicator(0, Qt.AscendingOrder)
        self.table.setItemDelegate(TableDelegate(self))
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)

        self.setCentralWidget(self.table)

    def closeEvent(self, event):
        if self.convert_pool.activeThreadCount() > 0:
            if prompt.yes_no('Cancel all conversions in progress?'):
                self.abort()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def dragEnterEvent(self, event):
        self.update_paths(drag_drop_paths(event))
        if self.paths:
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        event.accept()
        self.load_paths()

    def keyReleaseEvent(self, event):
        super(VideoConverter, self).keyReleaseEvent(event)
        if event.key() == Qt.Key_Delete:
            rows = set()
            for index in self.table.selectedIndexes():
                rows.add(index.row())
            if rows and prompt.yes_no('Delete the selected movies?'):
                for row in sorted(rows, reverse=True):
                    title = self.table.item(row, 0).text()
                    del self.movies[title]
                    self.table.removeRow(row)

    def update_paths(self, paths):
        self.paths.clear()
        for path in paths:
            if os.path.isfile(path):
                if self.extensions_regex.search(path):
                    self.paths.append(path)
            else:
                for p in search(path, pattern=self.extensions_regex,
                                levels=None, regex_flags=re.IGNORECASE):
                    self.paths.append(p)

    def load_paths(self):
        for path in self.paths:
            worker = LoadMovieWorker(path)
            worker.finished.connect(self.add_movie)
            self.load_pool.start(worker)

    def abort(self):
        self.event_stop.set()
        while self.convert_pool.activeThreadCount() > 0:
            time.sleep(0.1)
        for row in range(self.table.rowCount()):
            progress = self.table.cellWidget(row, 2)
            value = progress.value()
            if value >= 0 and value != 100:
                progress.setFormat('Aborted %p%')
                title = self.table.item(row, 0).text()
                while True:
                    try:
                        os.remove(self.movies[title].convert_path)
                        break
                    except PermissionError:  # file is still in use
                        time.sleep(0.1)
                    except FileNotFoundError:
                        break

    def add_movie(self, movie):
        self.mutex.lock()
        self.table.setSortingEnabled(False)

        self.movies[movie.title] = movie

        n = self.table.rowCount()
        self.table.setRowCount(n + 1)

        title = QtWidgets.QTableWidgetItem(f'{movie.title}')
        self.table.setItem(n, 0, title)

        subtitles = QtWidgets.QComboBox()
        subtitles.addItem('', userData={})
        for key, value in movie.subtitles.items():
            subtitles.addItem(key, userData=value)
        subtitles.currentIndexChanged.connect(partial(self.on_load_subtitle, movie.title))
        subtitles.setAccessibleName(movie.title)
        self.table.setCellWidget(n, 1, subtitles)

        progress = QtWidgets.QProgressBar()
        progress.setTextVisible(True)
        progress.setAlignment(Qt.AlignCenter)
        self.table.setCellWidget(n, 2, progress)

        self.table.setSortingEnabled(True)
        self.mutex.unlock()

    def convert(self):
        self.event_stop.clear()
        for row in range(self.table.rowCount()):
            title = self.table.item(row, 0).text()
            subtitles = self.table.cellWidget(row, 1)
            progress = self.table.cellWidget(row, 2)
            progress.setFormat('%p%')
            progress.reset()

            movie = self.movies[title]
            movie.subtitle = subtitles.itemData(subtitles.currentIndex())

            worker = ConvertMovieWorker(movie, self.event_stop)
            worker.signaler.percentage.connect(progress.setValue)
            worker.signaler.error.connect(progress.setFormat)
            self.convert_pool.start(worker)

    def find_combobox(self, title: str) -> QtWidgets.QComboBox:
        for row in range(self.table.rowCount()):
            combobox = cast(QtWidgets.QComboBox, self.table.cellWidget(row, 1))
            if combobox.accessibleName() == title:
                return combobox

    def on_load_subtitle(self, title: str, index: int) -> None:
        combobox = self.find_combobox(title)
        combobox.setToolTip('')
        info = combobox.itemData(index)
        if not info:
            return

        movie = self.movies[title]
        load_subtitles = LoadSubtitleWorker(movie, info)
        load_subtitles.signaler.finished.connect(self.on_change_tooltip)
        self.subtitle_workers.append(load_subtitles)
        self.subtitle_pool.start(load_subtitles)

    def on_change_tooltip(self, title: str, subtitles: list[str]) -> None:
        combobox = self.find_combobox(title)
        combobox.setToolTip(''.join(subtitles[:25]))
        for worker in self.subtitle_workers:
            if worker.title == title:
                break
        self.subtitle_workers.remove(worker)  # noqa: worker must be in the list

    def open(self, file_or_folder):
        if file_or_folder:
            self.update_paths([file_or_folder])
            self.load_paths()

    def open_folder(self):
        self.open(prompt.folder(directory=self.config.get('root_dir')))

    def open_filename(self):
        extensions = ' *.'.join(self.extensions)
        self.open(prompt.filename(
            filters=f'Video (*.{extensions})',
            directory=self.config.get('root_dir')
        ))


def ffmpeg_version():
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True)
    except FileNotFoundError:
        f = prompt.filename(title='Select the ffmpeg executable',
                            filters={'ffmpeg': '.exe'})
        if not f:
            return
        os.environ['PATH'] += os.pathsep + os.path.dirname(f)
        return ffmpeg_version()
    else:
        version = re.match(r'ffmpeg version ([\d.]+)', result.stdout.decode())
        if not version:
            prompt.critical('Cannot parse ffmpeg version')
            return
        return version.group(1)


def icon(filename):
    return to_qicon(os.path.join(os.path.dirname(__file__), 'images', filename))


def run():
    version = ffmpeg_version()
    if version is None:
        sys.exit('ffmpeg not found')

    config = {}
    if len(sys.argv) > 1:
        import json
        with open(sys.argv[1]) as fp:
            config = json.load(fp)

    app = application()
    main = VideoConverter(config)
    main.setWindowTitle(f'MP4 Converter || ffmpeg {version}')
    main.setWindowIcon(icon('favicon.ico'))
    rect = screen_geometry(main)
    main.resize(rect.width()//2, rect.height()//2)
    main.show()
    sys.exit(app.exec())
