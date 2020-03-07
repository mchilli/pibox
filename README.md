# PiBox

PiBox is a music player for a local device, controlled over the network with the WebUI or even a rotary encoder with or without a 16x2 lcd display, directly on a headless device. Originally designed only for a Raspberry Pi it can be used (as far as I know) on every debian based operating system, as a nice remote controlled music player :sunglasses:.

##### The WebUI:

<img src="https://github.com/mchilli/pibox/blob/master/images/webui001.png?raw=true" height="150"> <img src="https://github.com/mchilli/pibox/blob/master/images/webui002.png?raw=true" height="150"> <img src="https://github.com/mchilli/pibox/blob/master/images/webui003.png?raw=true" height="150"> <img src="https://github.com/mchilli/pibox/blob/master/images/webui004.png?raw=true" height="150"> <img src="https://github.com/mchilli/pibox/blob/master/images/webui005.png?raw=true" height="150">

#### History:

The project start early 2017 and with this I started learn to code python (thats the point why there are some old comments in the main python script :innocent:).The idea behind was to give my kids a device where they can listen to some audiobooks for childrens. So I buyed a Raspberry Pi Zero, a rotary encoder, a 16x2 LCD display, a HiFiBerry MiniAMP and build all together in an old speaker that I still had in my basement.

Here some project images, how the PiBoxes look like:\
<img src="https://github.com/mchilli/pibox/blob/master/images/build.png?raw=true" height="150"> <img src="https://github.com/mchilli/pibox/blob/master/images/complete.png?raw=true" height="150"> <img src="https://github.com/mchilli/pibox/blob/master/images/display.png?raw=true" height="150">

#### Dependecies:

python3 (version >= 3.3):

	sudo apt install python3.X

VLC Player (for better performance, version >= 3.0):

	sudo apt install vlc

##### Optional Raspberry Pi dependecies:

The display and rotary encoder are disabled by default, but you can enable it in the WebUI under system -> config. In this configuration you can also insert all necessary values, like the display address, the gpio-pins for the rot-enc etc..

To use the 16x2 LCD display with I2C, activate I2C under:

    sudo raspi-config

add following lines at the bottom of /etc/modules:

    i2c-bcm2708
    i2c-dev

install necessary I2C tools:

	sudo apt-get install python3-smbus i2c-tools

after reboot, test I2C connection and find out the display address:

	sudo i2cdetect -y 1

To use a "rotary encoder" the script need the python3 gpio lib, if not already installed, use:

	sudo apt-get install python3-rpi.gpio

#### Install & Use:

Download the zip-file and copy the "PiBox" folder to where ever you want. You can use the systemd service file under "etc" to start it automatically on startup, but you must change the path to your "pibox.py" and the user.

On first start PiBox use the default values, so it try to use the **system wide volume control**. If this is not possible it uses the VLC internal software volume control. If you want always the software volume you can check "**force softvol**" in the configuration.

The default port for the WebUI is **8080** it can be changed in config, but remember ports below 1024 require root privileges.

**Start PiBox with:**

	/path/to/PiBox/pibox.py

Check the WebUI under:

[http://localhost:8080](http://localhost:8080 "http://localhost:8080")

##### Theming:

There are two diffrent type of themes, a global and a local. The global theme will used on every device as the default theme and the local theme can be set per device and will be stored in the browsers local storage (like a cookie).

#### special thanks for this libraries I used in this project:

- [Python vlc bindings](https://github.com/oaubert/python-vlc)
- [Python websocket-server](https://github.com/Pithikos/python-websocket-server)
- [jQuery](https://jquery.com/)
- [jQuery contextMenu](https://swisnl.github.io/jQuery-contextMenu/)
- [List.js](https://listjs.com/)
- [iro.js](https://iro.js.org/)
- [Font Awesome](https://fontawesome.com/)
