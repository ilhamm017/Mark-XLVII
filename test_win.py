import ctypes

def list_visible_windows():
    user32 = ctypes.windll.user32
    
    def callback(hwnd, lParam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                print(f"HWND: {hwnd} | Title: {buff.value}")
        return True
        
    cb = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)(callback)
    user32.EnumWindows(cb, 0)

if __name__ == "__main__":
    list_visible_windows()
