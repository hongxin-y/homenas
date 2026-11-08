from setuptools import find_packages, setup

setup(
    name="homenas",
    version="0.1.0",
    package_dir={"": "backend"},
    packages=find_packages("backend"),
)

