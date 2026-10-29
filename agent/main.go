// scanwise-agent: native HID keyboard capture for ScanWise Engineering Mode.
//
// Reads key events straight from the OS input layer (Linux evdev, Windows Raw
// Input), with per-device identity and kernel timestamps, and streams them to
// the Engineering Mode page over Server-Sent Events on 127.0.0.1.
package main

import (
	"flag"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"
)

var version = "0.1.0"

type listFlag []string

func (l *listFlag) String() string { return strings.Join(*l, ",") }
func (l *listFlag) Set(v string) error {
	for _, p := range strings.Split(v, ",") {
		if p = strings.TrimSpace(p); p != "" {
			*l = append(*l, p)
		}
	}
	return nil
}

var defaultOrigins = []string{"http://localhost:5000", "http://127.0.0.1:5000"}

func main() {
	var origins listFlag
	listen := flag.String("listen", "127.0.0.1:47800", "loopback address to listen on")
	flag.Var(&origins, "allow-origin", "page origin allowed to connect (repeatable or comma-separated); default "+strings.Join(defaultOrigins, ", "))
	allowNoOrigin := flag.Bool("allow-no-origin", false, "accept requests without an Origin header (curl / scripts)")
	replay := flag.String("replay", "", "scanwise-capture JSON file to expose as a replay device")
	replaySpeed := flag.Float64("replay-speed", 1, "replay speed multiplier")
	replayLoop := flag.Bool("replay-loop", false, "loop the replay")
	noNative := flag.Bool("no-native", false, "disable the native OS source (replay only)")
	list := flag.Bool("list", false, "print keyboard devices and exit")
	device := flag.String("device", "", "device id to select at startup")
	grab := flag.Bool("grab", false, "with -device: exclusive grab (Linux) so scans don't also type into other apps")
	showVersion := flag.Bool("version", false, "print version and exit")
	flag.Parse()

	if *showVersion {
		fmt.Println("scanwise-agent", version)
		return
	}
	if len(origins) == 0 {
		origins = defaultOrigins
	}

	var sources []Source
	if !*noNative {
		if src := newNativeSource(); src != nil {
			sources = append(sources, src)
		}
	}
	if *replay != "" {
		rs, err := newReplaySource(*replay, *replaySpeed, *replayLoop, nowMs)
		if err != nil {
			log.Fatalf("replay: %v", err)
		}
		sources = append(sources, rs)
	}
	if len(sources) == 0 {
		log.Fatal("no capture sources available on this platform (use -replay)")
	}

	if *list {
		for _, src := range sources {
			ds, err := src.Devices()
			if err != nil {
				fmt.Fprintf(os.Stderr, "%s: %v\n", src.Kind(), err)
			}
			for _, d := range ds {
				mark := " "
				if d.LikelyScanner {
					mark = "*"
				}
				fmt.Printf("%s %-22s %s:%s  %-40s %s\n", mark, d.ID, d.VendorID, d.ProductID, d.Name, d.ScannerReason)
			}
		}
		return
	}

	host, _, err := net.SplitHostPort(*listen)
	if err != nil || !isLoopbackHost(host) {
		log.Fatalf("-listen must be a loopback address (got %q)", *listen)
	}

	srv := NewServer(sources, origins, *allowNoOrigin, version)
	if *device != "" {
		if err := srv.Select(*device, *grab); err != nil {
			log.Fatalf("select %s: %v", *device, err)
		}
	}

	ln, err := net.Listen("tcp", *listen)
	if err != nil {
		log.Fatal(err)
	}
	httpSrv := &http.Server{Handler: srv.Handler(), ReadHeaderTimeout: 5 * time.Second}
	log.Printf("scanwise-agent %s listening on http://%s (allowed origins: %s)", version, ln.Addr(), strings.Join(origins, ", "))

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
	go func() {
		<-sig
		srv.release() // ungrab before exit
		httpSrv.Close()
	}()
	if err := httpSrv.Serve(ln); err != nil && err != http.ErrServerClosed {
		log.Fatal(err)
	}
}
