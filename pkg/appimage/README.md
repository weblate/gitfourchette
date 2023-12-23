This folder contains boilerplate to produce an AppImage with [python-appimage](https://github.com/niess/python-appimage).

From the repo's root directory, run:

```
./pkg/appimage/write-requirements.sh

python -m python-appimage build app -p 3.12 ./pkg/appimage
```
