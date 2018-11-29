from setuptools import setup

setup(
    name='dcom',
    version='0.0.1',
    packages=['dcom'],
    url='https://github.com/emre/dcom',
    license='MIT',
    author='Emre Yilmaz',
    author_email='mail@emreyilmaz.me',
    description='dcom',
    entry_points={
        'console_scripts': [
            'dcom = dcom.main:main',
        ],
    },
    install_requires=[
        "lightstee", "discord.py", "python-dotenv"
    ]
)
