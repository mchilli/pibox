from RPi import GPIO
import time
import threading


class Rotary_Encoder:
    def __init__(self, clk_pin, dt_pin, turn_callback=None,
                 sw_pin=None, button_callback=None,
                 longpress_delay=1.0, button_long_callback=None):
        self.clk = clk_pin
        self.dt = dt_pin
        self.currentClk = 1
        self.currentDt = 1
        self.lockRotary = threading.Lock()
        self.turn_callback = turn_callback

        self.sw = sw_pin
        self.button_callback = button_callback
        self.longpress_delay = longpress_delay
        if button_long_callback:
            self.button_long_callback = button_long_callback
        else:
            self.button_long_callback = button_callback
        self.lockButton = threading.Lock()

        self.clkLevel = 0
        self.dtLevel = 0

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.clk, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.dt, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        GPIO.add_event_detect(self.clk, GPIO.RISING, self._turn_callback)
        GPIO.add_event_detect(self.dt, GPIO.RISING, self._turn_callback)

        if self.sw:
            GPIO.setup(self.sw, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.add_event_detect(self.sw, GPIO.FALLING, self._button_callback,
                                  bouncetime=500)

    def clean(self):
        GPIO.remove_event_detect(self.clk)
        GPIO.remove_event_detect(self.dt)
        GPIO.remove_event_detect(self.sw)
        GPIO.cleanup()

    def _button_callback_old(self, channel):
        start_time = time.time()
        while GPIO.input(channel) == 0:
            if (time.time() - start_time) >= self.longpress_delay:
                break
            time.sleep(.1)
        if time.time() - start_time >= self.longpress_delay:
            if self.button_long_callback:
                self.button_long_callback()
            else:
                self.button_callback()
        elif time.time() - start_time >= .1:
            self.button_callback()

    def _button_callback(self, channel):
        start_time = time.time()
        self.lockButton.acquire(timeout=self.longpress_delay + 1)
        for i in range(int(self.longpress_delay * 10) + 1):
            if (time.time() - start_time) >= self.longpress_delay:
                self.button_long_callback()
                self.lockButton.release()
                return
            elif GPIO.input(channel) == 1:
                if time.time() - start_time >= .1:
                    self.button_callback()
                self.lockButton.release()
                return
            time.sleep(.1)
        self.lockButton.release()

    def _turn_callback(self, channel):
        switchClk = GPIO.input(self.clk)
        switchDt = GPIO.input(self.dt)
        if self.currentClk == switchClk and self.currentDt == switchDt:
            return
        self.currentClk = switchClk
        self.currentDt = switchDt
        if (switchClk and switchDt):
            self.lockRotary.acquire(timeout=1)
            if channel == self.dt:
                self.turn_callback(False)
            else:
                self.turn_callback(True)
            self.lockRotary.release()
        return


if __name__ == '__main__':
    clk = 17
    dt = 27
    sw = 22

    def on_turn(drift):
        global counter
        if drift:
            counter += 1
        else:
            counter -= 1
        print(counter)

    def on_press():
        print("short press")

    try:
        Rot_Enc = Rotary_Encoder(clk, dt, turn_callback=on_turn, sw_pin=sw,
                                 button_callback=on_press)
        while True:
            pass
    except KeyboardInterrupt:
        Rot_Enc.clean()
    finally:
        Rot_Enc.clean()
