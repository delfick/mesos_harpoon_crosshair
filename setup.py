from setuptools import setup

setup(
      name = "mesos_harpoon_crosshair"
    , version = "0.1"
    , py_modules = ['mesos_harpoon_crosshair']

    , install_requires =
      [ "docker-harpoon>=0.7.2"
      , "option_merge_passwords==0.1"
      , "marathon==0.8.10"
      ]

    , extras_require =
      { "tests":
        [ "noseOfYeti>=1.4.9"
        , "nose"
        , "mock"
        , "boto"
        ]
      }

    , entry_points =
      { "harpoon.crosshairs": ["mesos = mesos_harpoon_crosshair"]
      }

    # metadata for upload to PyPI
    , url = "http://github.com/delfick/mesos_harpoon_crosshair"
    , author = "Stephen Moore"
    , author_email = "delfick755@gmail.com"
    , description = "Crosshair for deploying images from harpoon into mesos"
    , license = "MIT"
    )
