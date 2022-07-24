Convert a video to MP4 format and maybe embed English subtitles.

Requires `ffmpeg <https://ffmpeg.org/>`_ to be installed or to be available on `PATH`.

Install
-------
.. code-block:: console

   pip install git+https://github.com/jborbely/convert-mp4.git

Usage
-----
Can be run with or without a configuration file

.. code-block:: console

   convert-mp4 [config.json]

Configuration File
------------------
The following key-value pairs are supported:

* root_dir: (str) directory to initially start in when prompted to select a video
* extensions: (list[str]) the file extensions that can be converted

For example,

.. code-block:: json

   {
     "root_dir": "C:\\Videos\\Movies and TV shows",
     "extensions": ["avi", "mkv", "mp4"]
   }
