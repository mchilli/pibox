# coding: utf8

import smbus, time

############## Variablen
I2C_ADDR = 0x27
MASK_RS = 0x01
MASK_RW = 0x02
MASK_E = 0x04
SHIFT_BACKLIGHT = 3
SHIFT_DATA = 4
############## Variablen

############################################################ I2C API
class LCD_API:
    LCD_CLR = 0x01              # DB0: clear display
    LCD_HOME = 0x02             # DB1: return to home position

    LCD_ENTRY_MODE = 0x04       # DB2: set entry mode
    LCD_ENTRY_INC = 0x02        # --DB1: increment
    LCD_ENTRY_SHIFT = 0x01      # --DB0: shift

    LCD_ON_CTRL = 0x08          # DB3: turn lcd/cursor on
    LCD_ON_DISPLAY = 0x04       # --DB2: turn display on
    LCD_ON_CURSOR = 0x02        # --DB1: turn cursor on
    LCD_ON_BLINK = 0x01         # --DB0: blinking cursor

    LCD_MOVE = 0x10             # DB4: move cursor/display
    LCD_MOVE_DISP = 0x08        # --DB3: move display (0-> move cursor)
    LCD_MOVE_RIGHT = 0x04       # --DB2: move right (0-> left)

    LCD_FUNCTION = 0x20         # DB5: function set
    LCD_FUNCTION_8BIT = 0x10    # --DB4: set 8BIT mode (0->4BIT mode)
    LCD_FUNCTION_2LINES = 0x08  # --DB3: two lines (0->one line)
    LCD_FUNCTION_10DOTS = 0x04  # --DB2: 5x10 font (0->5x7 font)
    LCD_FUNCTION_RESET = 0x30   # See "Initializing by Instruction" section

    LCD_CGRAM = 0x40            # DB6: set CG RAM address
    LCD_DDRAM = 0x80            # DB7: set DD RAM address

    LCD_RS_CMD = 0
    LCD_RS_DATA = 1

    LCD_RW_WRITE = 0
    LCD_RW_READ = 1
    
    def __init__(self, num_lines, num_columns):
        self.num_lines = num_lines
        if self.num_lines > 4:
            self.num_lines = 4
        self.num_columns = num_columns
        if self.num_columns > 40:
            self.num_columns = 40
        self.cursor_x = 0
        self.cursor_y = 0
        self.backlight = True
        self.display_off()
        self.backlight_on()
        self.clear()
        self.hal_write_command(self.LCD_ENTRY_MODE | self.LCD_ENTRY_INC)
        self.hide_cursor()
        self.display_on()

    def clear(self):
        """Clears the LCD display and moves the cursor to the top left
        corner.
        """
        self.hal_write_command(self.LCD_CLR)
        self._delay_microseconds(3000)  # 3000 microsecond sleep, clearing the display takes a long time
        self.hal_write_command(self.LCD_HOME)
        self._delay_microseconds(3000)  # this command takes a long time!
        self.cursor_x = 0
        self.cursor_y = 0

    def show_cursor(self):
        """Causes the cursor to be made visible."""
        self.hal_write_command(self.LCD_ON_CTRL | self.LCD_ON_DISPLAY |
                               self.LCD_ON_CURSOR)

    def hide_cursor(self):
        """Causes the cursor to be hidden."""
        self.hal_write_command(self.LCD_ON_CTRL | self.LCD_ON_DISPLAY)

    def blink_cursor_on(self):
        """Turns on the cursor, and makes it blink."""
        self.hal_write_command(self.LCD_ON_CTRL | self.LCD_ON_DISPLAY |
                               self.LCD_ON_CURSOR | self.LCD_ON_BLINK)

    def blink_cursor_off(self):
        """Turns on the cursor, and makes it no blink (i.e. be solid)."""
        self.hal_write_command(self.LCD_ON_CTRL | self.LCD_ON_DISPLAY |
                               self.LCD_ON_CURSOR)

    def display_on(self):
        """Turns on (i.e. unblanks) the LCD."""
        self.hal_write_command(self.LCD_ON_CTRL | self.LCD_ON_DISPLAY)

    def display_off(self):
        """Turns off (i.e. blanks) the LCD."""
        self.hal_write_command(self.LCD_ON_CTRL)

    def backlight_on(self):
        """Turns the backlight on.

        This isn't really an LCD command, but some modules have backlight
        controls, so this allows the hal to pass through the command.
        """
        self.backlight = True
        self.hal_backlight_on()

    def backlight_off(self):
        """Turns the backlight off.

        This isn't really an LCD command, but some modules have backlight
        controls, so this allows the hal to pass through the command.
        """
        self.backlight = False
        self.hal_backlight_off()
    
    def lcd_backlight(self, state):
        if state in ("on","On","ON",1):
            self.backlight_on()
        elif state in ("off","Off","OFF",0):
            self.backlight_off()
        else:
            print("Unknown State!")
    
    def move_to(self, cursor_x, cursor_y):
        """Moves the cursor position to the indicated position. The cursor
        position is zero based (i.e. cursor_x == 0 indicates first column).
        """
        self.cursor_x = cursor_x
        self.cursor_y = cursor_y
        addr = cursor_x & 0x3f
        if cursor_y & 1:
            addr += 0x40    # Lines 1 & 3 add 0x40
        if cursor_y & 2:
            addr += 0x14    # Lines 2 & 3 add 0x14
        self.hal_write_command(self.LCD_DDRAM | addr)

    def putchar(self, char):
        """Writes the indicated character to the LCD at the current cursor
        position, and advances the cursor by one position.
        """
        # One millisecond delay to prevent writing too quickly.
        self._delay_microseconds(1000)
        if char != '\n':
            self.hal_write_data(char)
            self.cursor_x += 1
        if self.cursor_x >= self.num_columns or char == '\n':
            self.cursor_x = 0
            self.cursor_y += 1
            if self.cursor_y >= self.num_lines:
                self.cursor_y = 0
            self.move_to(self.cursor_x, self.cursor_y)

    def putstr(self, string):
        """Write the indicated string to the LCD at the current cursor
        position and advances the cursor position appropriately.
        """
        for char in string:
            self.putchar(char)
    
    def custom_char(self, location, charmap):
        """Write a character to one of the 8 CGRAM locations, available
        as chr(0) through chr(7).
        """
        location &= 0x7
        self.hal_write_command(self.LCD_CGRAM | (location << 3))
        self._delay_microseconds(40)
        for i in range(8):
            self.hal_write_data(charmap[i])
            self._delay_microseconds(40)
        self.move_to(self.cursor_x, self.cursor_y)

    def lcd_display_string(self, string, line=1, align=1, start_pos=1):
        self.move_to(0, line-1)
        string = self.change_chars(string)
        if align == 0:                            #append to specify position
            self.move_to(start_pos-1, line-1)
        elif align == 1:                        #left align
            string = string.ljust(16)
        elif align == 2:                        #center align
            string = string.center(16)
        elif align == 3:                        #right align
            string = string.rjust(16)
        for char in string:
            self.putchar(ord(char))
            # self.putchar(char)
            
    def change_chars(self, string):
        try:
            # string = string.encode('utf-8')
            string = string.replace('ä', chr(225))
            string = string.replace('ö', chr(239))
            string = string.replace('ü', chr(245))
            string = string.replace('Ä', chr(225))
            string = string.replace('Ö', chr(239))
            string = string.replace('Ü', chr(245))
            string = string.replace('ß', chr(226))
            string = string.replace('°', chr(223))
            string = string.replace('µ', chr(228))
            string = string.replace('´', chr(96))
            string = string.replace('€', chr(227))
            string = string.replace('–', '-')
            string = string.replace('“', '"')
            string = string.replace('”', '"')
            string = string.replace('„', '"')
            string = string.replace('’', '\'')
            string = string.replace('‘', '\'')
        except:
            return string
        return string

    def _delay_microseconds(self, microseconds):
        '''Busy wait in loop because delays are generally very short (few microseconds).'''
        end = time.time() + (microseconds/1000000.0)
        while time.time() < end:
            pass

############################################################ I2C API

############################################################ I2C LCD
class I2C_LCD(LCD_API):
    """Implements a HD44780 character LCD connected via PCF8574 on I2C."""
    def __init__(self, port, i2c_addr, num_lines, num_columns):
        self.port = port
        self.i2c_addr = i2c_addr
        self.bus = smbus.SMBus(port)
        self.bus.write_byte(self.i2c_addr, 0)
        time.sleep(0.020)    # Allow LCD time to powerup
        # Send reset 3 times
        self.hal_write_init_nibble(self.LCD_FUNCTION_RESET)
        time.sleep(0.005)   # need to delay at least 4.1 msec
        self.hal_write_init_nibble(self.LCD_FUNCTION_RESET)
        time.sleep(0.001)
        self.hal_write_init_nibble(self.LCD_FUNCTION_RESET)
        time.sleep(0.001)
        # Put LCD into 4 bit mode
        self.hal_write_init_nibble(self.LCD_FUNCTION)
        time.sleep(0.001)
        LCD_API.__init__(self, num_lines, num_columns)
        cmd = self.LCD_FUNCTION
        if num_lines > 1:
            cmd |= self.LCD_FUNCTION_2LINES
        self.hal_write_command(cmd)

    def hal_write_init_nibble(self, nibble):
        """Writes an initialization nibble to the LCD.

        This particular function is only used during initialization.
        """
        byte = ((nibble >> 4) & 0x0f) << SHIFT_DATA
        self.bus.write_byte(self.i2c_addr, byte | MASK_E)
        self.bus.write_byte(self.i2c_addr, byte)

    def hal_backlight_on(self):
        """Allows the hal layer to turn the backlight on."""
        self.bus.write_byte(self.i2c_addr, 1 << SHIFT_BACKLIGHT)

    def hal_backlight_off(self):
        """Allows the hal layer to turn the backlight off."""
        self.bus.write_byte(self.i2c_addr, 0)

    def hal_write_command(self, cmd):
        """Writes a command to the LCD.

        Data is latched on the falling edge of E.
        """
        byte = ((self.backlight << SHIFT_BACKLIGHT) |
                (((cmd >> 4) & 0x0f) << SHIFT_DATA))
        self.bus.write_byte(self.i2c_addr, byte | MASK_E)
        self.bus.write_byte(self.i2c_addr, byte)
        byte = ((self.backlight << SHIFT_BACKLIGHT) |
                ((cmd & 0x0f) << SHIFT_DATA))
        self.bus.write_byte(self.i2c_addr, byte | MASK_E)
        self.bus.write_byte(self.i2c_addr, byte)
        if cmd <= 3:
            # The home and clear commands require a worst
            # case delay of 4.1 msec
            time.sleep(0.005)

    def hal_write_data(self, data):
        """Write data to the LCD."""
        byte = (MASK_RS |
                (self.backlight << SHIFT_BACKLIGHT) |
                (((data >> 4) & 0x0f) << SHIFT_DATA))
        self.bus.write_byte(self.i2c_addr, byte | MASK_E)
        self.bus.write_byte(self.i2c_addr, byte)
        byte = (MASK_RS |
                (self.backlight << SHIFT_BACKLIGHT) |
                ((data & 0x0f) << SHIFT_DATA))
        self.bus.write_byte(self.i2c_addr, byte | MASK_E)
        self.bus.write_byte(self.i2c_addr, byte)

############################################################ I2C LCD

if __name__ == '__main__':
    def define_custom_char():
        LCD.custom_char(0, bytearray([0x00,0x08,0x0c,0x0e,0x0c,0x08,0x00,0x00]))  # play
        LCD.custom_char(1, bytearray([0x00,0x1f,0x1f,0x1f,0x1f,0x1f,0x00,0x00]))  # stop
        LCD.custom_char(2, bytearray([0x00,0x1b,0x1b,0x1b,0x1b,0x1b,0x00,0x00]))  # pause
        LCD.custom_char(3, bytearray([0x1f,0x11,0x0a,0x04,0x0a,0x11,0x1f,0x00]))  # wait
        LCD.custom_char(4, bytearray([0x00,0x0e,0x15,0x17,0x11,0x0e,0x00,0x00]))  # clock
        LCD.custom_char(5, bytearray([0x0E,0x1B,0x1F,0x1F,0x1F,0x1F,0x1F,0x1F]))  # 83%
        LCD.custom_char(6, bytearray([0x00,0x00,0x0a,0x00,0x0e,0x11,0x00,0x00]))  # badey
        LCD.custom_char(7, bytearray([0x00,0x00,0x0a,0x00,0x11,0x0e,0x00,0x00]))  # smiley

    LCD = I2C_LCD(1, I2C_ADDR, 2, 16)
    define_custom_char()
    LCD.lcd_display_string("Hallo %s" % chr(7), 1, 2)
    time.sleep(5)
    LCD.clear()
    LCD.lcd_backlight("off")