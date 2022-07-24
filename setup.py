from setuptools import setup

setup(
    name='convert-mp4',
    version='0.1.0',
    author='jborbely',
    description='Convert a video to MP4 format and maybe embed English subtitles',
    license='MIT',
    install_requires=[
        'msl-qt[PySide6] @ git+https://github.com/MSLNZ/msl-qt.git',
        'msl-io @ git+https://github.com/MSLNZ/msl-io.git',
    ],
    entry_points={
        'console_scripts': [
            'convert-mp4 = convert_mp4:run',
        ],
    },
    packages=['convert_mp4'],
    include_package_data=True,
    zip_safe=False,
)
