# -*- coding: utf-8 -*-
from setuptools import setup, find_packages


requirements = [
    "dbus-next;sys_platform=='linux'",
    "importlib_resources;python_version<'3.9'",
    "packaging",
    "rubicon-objc;sys_platform=='darwin'",
    "winrt;sys_platform=='win32'",
]

dev_requires = [
    "black",
    "bump2version",
    "flake8",
    "mypy",
    "pre-commit",
    "pytest",
    "pytest-cov",
]

docs_require = [
    "sphinx",
    "m2r2",
    "sphinx-autoapi",
    "sphinx_rtd_theme",
]

setup(
    author="Sam Schott",
    author_email="sam.schott@outlook.com",
    python_requires=">=3.6",
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
    description="Python library for cross-platform desktop notifications",
    setup_requires=["wheel"],
    install_requires=requirements,
    extras_require={
        "dev": dev_requires,
        "docs": docs_require,
    },
    package_data={
        "desktop_notifier": ["resources/*"],
    },
    license="MIT license",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    include_package_data=True,
    keywords="desktop-notifier",
    name="desktop-notifier",
    packages=find_packages("src"),
    package_dir={"": "src"},
    url="https://github.com/samschott/desktop-notifier",
    version="3.2.3",
    zip_safe=False,
)
