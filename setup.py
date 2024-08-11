from setuptools import setup, find_packages, find_namespace_packages

setup(
    name="promptview",
    version="0.1",
    author='Pavel Schudel',
    author_email='pavel1860@gmail.com',
    url='https://github.com/pavel1860/promptview',
    description="A modular chatboard package",
    packages=find_packages(),
    install_requires=[
        "numpy==1.26.4",
        "pydantic>=2.8.2, <3",
        "tiktoken==0.5.2",
        "pinecone-text==0.9.0",
        "scipy==1.11.4",
        "boto3==1.24.47",
        "openai==1.37.1",
        "langdetect==1.0.9",
        "qdrant-client==1.10.1",
        "docstring_parser==0.16",
        "iso-639==0.4.5",
    ],    
    classifiers=[
        # Classifiers help users find your project by categorizing it.
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.10',
)

