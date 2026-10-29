package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// captureFile is the Engineering Mode export format ("scanwise-capture").
type captureFile struct {
	Format string `json:"format"`
	Scans  []struct {
		Events []struct {
			T      float64 `json:"t"`
			Type   string  `json:"type"`
			Code   string  `json:"code"`
			Repeat bool    `json:"repeat"`
		} `json:"events"`
	} `json:"scans"`
}

// replaySource plays recorded captures with their original timing. It exists
// for demos and tests without scanner hardware.
type replaySource struct {
	path  string
	speed float64
	loop  bool
	gap   time.Duration
	clock func() float64
	data  *captureFile
}

func loadCapture(path string) (*captureFile, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var c captureFile
	if err := json.Unmarshal(b, &c); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	if c.Format != "scanwise-capture" {
		return nil, fmt.Errorf("%s: not a scanwise-capture file (format=%q)", path, c.Format)
	}
	if len(c.Scans) == 0 {
		return nil, fmt.Errorf("%s: no scans", path)
	}
	return &c, nil
}

func newReplaySource(path string, speed float64, loop bool, clock func() float64) (*replaySource, error) {
	c, err := loadCapture(path)
	if err != nil {
		return nil, err
	}
	if speed <= 0 {
		speed = 1
	}
	return &replaySource{path: path, speed: speed, loop: loop, gap: time.Second, clock: clock, data: c}, nil
}

func (s *replaySource) Kind() string { return "replay" }

func (s *replaySource) Devices() ([]Device, error) {
	name := strings.TrimSuffix(filepath.Base(s.path), filepath.Ext(s.path))
	return []Device{{
		ID: "replay:0", Name: fmt.Sprintf("Replay: %s (%d scans)", name, len(s.data.Scans)),
		Path: s.path, Kind: "replay", LikelyScanner: true, ScannerReason: "recorded capture",
	}}, nil
}

func (s *replaySource) Open(id string, grab bool, out chan<- KeyEvent) (func(), error) {
	if id != "replay:0" {
		return nil, fmt.Errorf("unknown replay device %q", id)
	}
	quit := make(chan struct{})
	done := make(chan struct{})
	go func() {
		defer close(done)
		sleep := func(d time.Duration) bool {
			select {
			case <-time.After(d):
				return true
			case <-quit:
				return false
			}
		}
		for {
			for _, scan := range s.data.Scans {
				if len(scan.Events) == 0 {
					continue
				}
				prev := scan.Events[0].T
				for _, ev := range scan.Events {
					if !sleep(time.Duration((ev.T - prev) / s.speed * float64(time.Millisecond))) {
						return
					}
					prev = ev.T
					select {
					case out <- KeyEvent{T: s.clock(), Type: ev.Type, Code: ev.Code, Repeat: ev.Repeat, Src: "replay", Device: id}:
					case <-quit:
						return
					}
				}
				if !sleep(s.gap) {
					return
				}
			}
			if !s.loop {
				return
			}
		}
	}()
	var once sync.Once
	return func() { once.Do(func() { close(quit); <-done }) }, nil
}
