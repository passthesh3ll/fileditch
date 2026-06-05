# FileDitch

![image](https://i.postimg.cc/02xLMrq6/image.png)

A python FileDitch client. You can upload files or entire folders to FileDitch, providing a simple command-line interface with progress tracking and optional logging of download links.

## Dependencies

- `requests`
- `requests_toolbelt`
- `tqdm`
- `colorama`

```bash
pip install requests requests-toolbelt tqdm colorama
```

## Example

Upload a file:

```bash
python fileditch.py /path/to/file.txt
```

![image](https://i.postimg.cc/4d2mKjmr/image.png)

Upload a folder:

```bash
python fileditch.py /path/to/dir/
```

Parallel upload:

```bash
python fileditch.py --parallel 3 /path/to/dir/
```
![image](https://i.postimg.cc/3JVmf0rV/image.png)

## Help

```
usage: fileditch.py [-h] [--log] [--wait WAIT] [--proxy [PROXY]] [--parallel PARALLEL]
                    path

upload files or folders to FileDitch

positional arguments:
  path                 path to the file or folder to upload

options:
  -h, --help           show this help message and exit
  --log                save upload links to _links.txt file
  --wait WAIT          seconds to wait between uploads
  --proxy [PROXY]      use proxy
  --parallel PARALLEL  number of parallel uploads

```
