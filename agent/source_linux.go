//go:build linux

package main

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"syscall"
	"unsafe"
)

// ioctl request numbers (asm-generic/ioctl.h): dir<<30 | size<<16 | type<<8 | nr.
func ioc(dir, typ, nr, size uintptr) uintptr { return dir<<30 | size<<16 | typ<<8 | nr }

const iocRead, iocWrite = 2, 1

func eviocgname(n uintptr) uintptr    { return ioc(iocRead, 'E', 0x06, n) }
func eviocgphys(n uintptr) uintptr    { return ioc(iocRead, 'E', 0x07, n) }
func eviocgbit(ev, n uintptr) uintptr { return ioc(iocRead, 'E', 0x20+ev, n) }

var (
	eviocgid      = ioc(iocRead, 'E', 0x02, 8)
	eviocgrab     = ioc(iocWrite, 'E', 0x90, 4)
	eviocsclockid = ioc(iocWrite, 'E', 0xa0, 4)
)

const clockMonotonic = 1

var busNames = map[uint16]string{0x03: "usb", 0x05: "bluetooth", 0x11: "i8042", 0x19: "host", 0x06: "virtual"}

type linuxSource struct {
	glob string
}

func newNativeSource() Source { return &linuxSource{glob: "/dev/input/event*"} }

func (s *linuxSource) Kind() string { return "evdev" }

func ioctlCall(f *os.File, call func(fd uintptr) syscall.Errno) error {
	rc, err := f.SyscallConn()
	if err != nil {
		return err
	}
	var errno syscall.Errno
	if cerr := rc.Control(func(fd uintptr) { errno = call(fd) }); cerr != nil {
		return cerr
	}
	if errno != 0 {
		return errno
	}
	return nil
}

// ioctl with a pointer argument.
func ioctl(f *os.File, req uintptr, arg unsafe.Pointer) error {
	return ioctlCall(f, func(fd uintptr) syscall.Errno {
		_, _, e := syscall.Syscall(syscall.SYS_IOCTL, fd, req, uintptr(arg))
		return e
	})
}

// ioctlVal with an integer argument passed by value (EVIOCGRAB, EVIOCSCLOCKID takes a pointer).
func ioctlVal(f *os.File, req uintptr, val uintptr) error {
	return ioctlCall(f, func(fd uintptr) syscall.Errno {
		_, _, e := syscall.Syscall(syscall.SYS_IOCTL, fd, req, val)
		return e
	})
}

func ioctlString(f *os.File, reqFn func(uintptr) uintptr) string {
	buf := make([]byte, 256)
	if err := ioctl(f, reqFn(uintptr(len(buf))), unsafe.Pointer(&buf[0])); err != nil {
		return ""
	}
	return strings.TrimRight(string(buf), "\x00")
}

// isKeyboard: the device reports EV_KEY and has letter keys A..Z.
func isKeyboard(f *os.File) bool {
	bits := make([]byte, 96) // KEY_MAX 0x2ff -> 768 bits
	if err := ioctl(f, eviocgbit(evKey, uintptr(len(bits))), unsafe.Pointer(&bits[0])); err != nil {
		return false
	}
	has := func(code int) bool { return bits[code/8]&(1<<(code%8)) != 0 }
	for _, code := range []int{30, 48, 46, 32, 18, 28} { // A B C D E Enter
		if !has(code) {
			return false
		}
	}
	return true
}

func (s *linuxSource) Devices() ([]Device, error) {
	paths, err := filepath.Glob(s.glob)
	if err != nil {
		return nil, err
	}
	sort.Strings(paths)
	var out []Device
	denied := 0
	for _, p := range paths {
		f, err := os.OpenFile(p, os.O_RDONLY, 0)
		if err != nil {
			if errors.Is(err, os.ErrPermission) {
				denied++
			}
			continue
		}
		if !isKeyboard(f) {
			f.Close()
			continue
		}
		var id [4]uint16 // bustype, vendor, product, version
		_ = ioctl(f, eviocgid, unsafe.Pointer(&id[0]))
		d := Device{
			ID:        "evdev:" + filepath.Base(p),
			Name:      ioctlString(f, eviocgname),
			Path:      p,
			Phys:      ioctlString(f, eviocgphys),
			Bus:       busNames[id[0]],
			VendorID:  fmt.Sprintf("%04x", id[1]),
			ProductID: fmt.Sprintf("%04x", id[2]),
			CanGrab:   true,
			Kind:      "evdev",
		}
		d.LikelyScanner, d.ScannerReason = detectScanner(d.Name, d.VendorID)
		f.Close()
		out = append(out, d)
	}
	if len(out) == 0 && denied > 0 {
		return nil, fmt.Errorf("permission denied on %d input device(s): add your user to the 'input' group (sudo usermod -aG input $USER, then log in again)", denied)
	}
	return out, nil
}

func (s *linuxSource) Open(id string, grab bool, out chan<- KeyEvent) (func(), error) {
	name := strings.TrimPrefix(id, "evdev:")
	if name == id || strings.ContainsAny(name, "/.") {
		return nil, fmt.Errorf("not an evdev device id: %q", id)
	}
	f, err := os.OpenFile("/dev/input/"+name, os.O_RDONLY, 0)
	if err != nil {
		return nil, err
	}
	if !isKeyboard(f) {
		f.Close()
		return nil, fmt.Errorf("%s is not a keyboard-class device", id)
	}
	clock := int32(clockMonotonic)
	_ = ioctl(f, eviocsclockid, unsafe.Pointer(&clock))
	if grab {
		// EVIOCGRAB takes the int by value.
		if err := ioctlVal(f, eviocgrab, 1); err != nil {
			f.Close()
			return nil, fmt.Errorf("exclusive grab failed: %w", err)
		}
	}

	wordSize := int(unsafe.Sizeof(uintptr(0)))
	size := inputEventSize(wordSize)
	tr := &evdevTranslator{device: id}
	var once sync.Once
	done := make(chan struct{})
	quit := make(chan struct{})
	go func() {
		defer close(done)
		buf := make([]byte, size*64)
		for {
			n, err := f.Read(buf)
			if err != nil {
				return
			}
			for _, raw := range parseInputEvents(buf[:n], wordSize) {
				if ev, ok := tr.translate(raw); ok {
					select {
					case out <- ev:
					case <-quit:
						return
					}
				}
			}
		}
	}()
	stop := func() {
		once.Do(func() {
			close(quit)
			if grab {
				_ = ioctlVal(f, eviocgrab, 0)
			}
			f.Close()
			<-done
		})
	}
	return stop, nil
}
