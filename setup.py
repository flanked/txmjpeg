from setuptools import setup, find_packages

setup(
      name='txmjpeg',
      version='0.1.0',
      description='Twisted Web MJPEG streamer',
      author='flanked',
      install_requires=['twisted>=13.0'],
      packages=find_packages())
