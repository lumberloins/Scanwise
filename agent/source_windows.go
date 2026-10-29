//go:build windows

package main

import (
	"fmt"
	"regexp"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"unsafe"
)

var (
	user32   = syscall.NewLazyDLL("user32.dll")
	kernel32 = syscall.NewLazyDLL("kernel32.dll")
	hid      = syscall.NewLazyDLL("hid.dll")

	pRegisterClassExW        = user32.NewProc("RegisterClassExW")
	pCreateWindowExW         = user32.NewProc("CreateWindowExW")
	pDestroyWindow           = user32.NewProc("DestroyWindow")
	pDefWindowProcW          = user32.NewProc("DefWindowProcW")
	pGetMessageW             = user32.NewProc("GetMessageW")
	pDispatchMessageW        = user32.NewProc("DispatchMessageW")
	pPostThreadMessageW      = user32.NewProc("PostThreadMessageW")
	pRegisterRawInputDevices = user32.NewProc("RegisterRawInputDevices")
	pGetRawInputData         = user32.NewProc("GetRawInputData")
	pGetRawInputDeviceList   = user32.NewProc("GetRawInputDeviceList")
	pGetRawInputDeviceInfoW  = user32.NewProc("GetRawInputDeviceInfoW")
	pGetModuleHandleW        = kernel32.NewProc("GetModuleHandleW")
	pGetCurrentThreadId      = kernel32.NewProc("GetCurrentThreadId")
	pCreateFileW             = kernel32.NewProc("CreateFileW")
	pCloseHandle             = kernel32.NewProc("CloseHandle")
	pHidDGetProductString    = hid.NewProc("HidD_GetProductString")
	pHidDGetManufacturer     = hid.NewProc("HidD_GetManufacturerString")
)

const (
	wmInput         = 0x00FF
	wmQuit          = 0x0012
	ridInput        = 0x10000003
	rimTypeKeyboard = 1
	ridevInputSink  = 0x00000100
	ridevRemove     = 0x00000001
	ridiDeviceName  = 0x20000007
	riKeyBreak      = 0x01
	riKeyE0         = 0x02
	riKeyE1         = 0x04
	hwndMessage     = ^uintptr(2) // (HWND)-3
	openExisting    = 3
	fileShareRW     = 3
	invalidHandle   = ^uintptr(0)
)

type rawInputDevice struct {
	UsagePage uint16
	Usage     uint16
	Flags     uint32
	Target    uintptr
}

type rawInputDeviceList struct {
	Device uintptr
	Type   uint32
}

type rawInputHeader struct {
	Type   uint32
	Size   uint32
	Device uintptr
	WParam uintptr
}

type rawKeyboard struct {
	MakeCode         uint16
	Flags            uint16
	Reserved         uint16
	VKey             uint16
	Message          uint32
	ExtraInformation uint32
}

type rawInputKeyboard struct {
	Header   rawInputHeader
	Keyboard rawKeyboard
}

type msg struct {
	Hwnd     uintptr
	Message  uint32
	WParam   uintptr
	LParam   uintptr
	Time     uint32
	PtX, PtY int32
	LPrivate uint32
}

type wndClassEx struct {
	Size       uint32
	Style      uint32
	WndProc    uintptr
	ClsExtra   int32
	WndExtra   int32
	Instance   uintptr
	Icon       uintptr
	Cursor     uintptr
	Background uintptr
	MenuName   *uint16
	ClassName  *uint16
	IconSm     uintptr
}

var vidPid = regexp.MustCompile(`(?i)VID_([0-9a-f]{4}).*PID_([0-9a-f]{4})`)

type windowsSource struct{}

func newNativeSource() Source { return &windowsSource{} }

func (s *windowsSource) Kind() string { return "rawinput" }

func deviceName(h uintptr) string {
	var size uint32
	pGetRawInputDeviceInfoW.Call(h, ridiDeviceName, 0, uintptr(unsafe.Pointer(&size)))
	if size == 0 {
		return ""
	}
	buf := make([]uint16, size+1)
	r, _, _ := pGetRawInputDeviceInfoW.Call(h, ridiDeviceName, uintptr(unsafe.Pointer(&buf[0])), uintptr(unsafe.Pointer(&size)))
	if int32(r) <= 0 {
		return ""
	}
	return syscall.UTF16ToString(buf)
}

// hidStrings opens the device path with no access rights (allowed for keyboards) to read its USB strings.
func hidStrings(path string) (manufacturer, product string) {
	p, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		return
	}
	h, _, _ := pCreateFileW.Call(uintptr(unsafe.Pointer(p)), 0, fileShareRW, 0, openExisting, 0, 0)
	if h == invalidHandle || h == 0 {
		return
	}
	defer pCloseHandle.Call(h)
	get := func(proc *syscall.LazyProc) string {
		buf := make([]uint16, 256)
		if r, _, _ := proc.Call(h, uintptr(unsafe.Pointer(&buf[0])), uintptr(len(buf)*2)); r == 0 {
			return ""
		}
		return syscall.UTF16ToString(buf)
	}
	return get(pHidDGetManufacturer), get(pHidDGetProductString)
}

func (s *windowsSource) Devices() ([]Device, error) {
	var n uint32
	size := unsafe.Sizeof(rawInputDeviceList{})
	pGetRawInputDeviceList.Call(0, uintptr(unsafe.Pointer(&n)), size)
	if n == 0 {
		return nil, nil
	}
	list := make([]rawInputDeviceList, n)
	r, _, err := pGetRawInputDeviceList.Call(uintptr(unsafe.Pointer(&list[0])), uintptr(unsafe.Pointer(&n)), size)
	if int32(r) < 0 {
		return nil, fmt.Errorf("GetRawInputDeviceList: %v", err)
	}
	var out []Device
	for _, d := range list[:r] {
		if d.Type != rimTypeKeyboard {
			continue
		}
		path := deviceName(d.Device)
		dev := Device{ID: fmt.Sprintf("rawinput:%x", d.Device), Path: path, Kind: "rawinput", CanGrab: false}
		if m := vidPid.FindStringSubmatch(path); m != nil {
			dev.VendorID, dev.ProductID = strings.ToLower(m[1]), strings.ToLower(m[2])
			dev.Bus = "usb"
		}
		mfr, prod := hidStrings(path)
		dev.Name = strings.TrimSpace(mfr + " " + prod)
		if dev.Name == "" {
			dev.Name = path
		}
		dev.LikelyScanner, dev.ScannerReason = detectScanner(dev.Name, dev.VendorID)
		out = append(out, dev)
	}
	return out, nil
}

func (s *windowsSource) Open(id string, grab bool, out chan<- KeyEvent) (func(), error) {
	if grab {
		return nil, fmt.Errorf("exclusive grab is not available with Windows Raw Input")
	}
	hexID := strings.TrimPrefix(id, "rawinput:")
	target, err := strconv.ParseUint(hexID, 16, 64)
	if err != nil || hexID == id {
		return nil, fmt.Errorf("not a rawinput device id: %q", id)
	}

	ready := make(chan error, 1)
	done := make(chan struct{})
	quit := make(chan struct{})
	var threadID uintptr

	go func() {
		defer close(done)
		runtime.LockOSThread()
		defer runtime.UnlockOSThread()
		threadID, _, _ = pGetCurrentThreadId.Call()

		inst, _, _ := pGetModuleHandleW.Call(0)
		cls, _ := syscall.UTF16PtrFromString("ScanWiseAgentRawInput")
		wc := wndClassEx{Size: uint32(unsafe.Sizeof(wndClassEx{})), WndProc: pDefWindowProcW.Addr(), Instance: inst, ClassName: cls}
		pRegisterClassExW.Call(uintptr(unsafe.Pointer(&wc))) // fails harmlessly if already registered
		hwnd, _, cerr := pCreateWindowExW.Call(0, uintptr(unsafe.Pointer(cls)), 0, 0, 0, 0, 0, 0, hwndMessage, 0, inst, 0)
		if hwnd == 0 {
			ready <- fmt.Errorf("CreateWindowEx: %v", cerr)
			return
		}
		defer pDestroyWindow.Call(hwnd)

		rid := rawInputDevice{UsagePage: 0x01, Usage: 0x06, Flags: ridevInputSink, Target: hwnd}
		if r, _, rerr := pRegisterRawInputDevices.Call(uintptr(unsafe.Pointer(&rid)), 1, unsafe.Sizeof(rid)); r == 0 {
			ready <- fmt.Errorf("RegisterRawInputDevices: %v", rerr)
			return
		}
		defer func() {
			rm := rawInputDevice{UsagePage: 0x01, Usage: 0x06, Flags: ridevRemove}
			pRegisterRawInputDevices.Call(uintptr(unsafe.Pointer(&rm)), 1, unsafe.Sizeof(rm))
		}()
		ready <- nil

		pressed := map[string]bool{}
		var m msg
		var ri rawInputKeyboard
		hdrSize := unsafe.Sizeof(rawInputHeader{})
		for {
			r, _, _ := pGetMessageW.Call(uintptr(unsafe.Pointer(&m)), 0, 0, 0)
			if int32(r) <= 0 { // WM_QUIT or error
				return
			}
			if m.Message == wmInput {
				size := uint32(unsafe.Sizeof(ri))
				n, _, _ := pGetRawInputData.Call(m.LParam, ridInput, uintptr(unsafe.Pointer(&ri)), uintptr(unsafe.Pointer(&size)), hdrSize)
				if int32(n) > 0 && ri.Header.Type == rimTypeKeyboard && uint64(ri.Header.Device) == target {
					kb := ri.Keyboard
					code, ok := codeForScancode(kb.MakeCode, kb.Flags&riKeyE0 != 0, kb.Flags&riKeyE1 != 0)
					if ok {
						ev := KeyEvent{T: nowMs(), Type: "down", Code: code, Src: "agent", Device: id, Scancode: int(kb.MakeCode)}
						if kb.Flags&riKeyE0 != 0 {
							ev.Scancode |= 0xE000
						}
						if kb.Flags&riKeyBreak != 0 {
							ev.Type = "up"
							delete(pressed, code)
						} else {
							ev.Repeat = pressed[code]
							pressed[code] = true
						}
						select {
						case out <- ev:
						case <-quit:
							return
						}
					}
				}
			}
			pDispatchMessageW.Call(uintptr(unsafe.Pointer(&m)))
		}
	}()

	if err := <-ready; err != nil {
		<-done
		return nil, err
	}
	var once sync.Once
	stop := func() {
		once.Do(func() {
			close(quit)
			pPostThreadMessageW.Call(threadID, wmQuit, 0, 0)
			<-done
		})
	}
	return stop, nil
}
