package main

import (
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"runtime"
	"strings"
	"sync"
	"time"
)

type selection struct {
	device Device
	grab   bool
	stop   func()
}

// Server exposes devices and streams key events over Server-Sent Events.
//
// Security model: the agent can read any keyboard, so
//   - it listens on loopback only,
//   - every request must carry an allowed Origin (browsers set it; this blocks other web pages),
//   - the Host header must be a loopback name (blocks DNS rebinding),
//   - nothing is streamed until a device is explicitly selected.
type Server struct {
	sources       []Source
	allowed       map[string]bool
	allowNoOrigin bool
	version       string

	selectMu  sync.Mutex // serializes Select/release so two clients can't race device opens
	mu        sync.Mutex
	sel       *selection
	clients   map[chan []byte]struct{}
	dropped   int
	events    chan KeyEvent
	keepAlive time.Duration
}

func NewServer(sources []Source, allowedOrigins []string, allowNoOrigin bool, version string) *Server {
	s := &Server{
		sources: sources, allowed: map[string]bool{}, allowNoOrigin: allowNoOrigin, version: version,
		clients: map[chan []byte]struct{}{}, events: make(chan KeyEvent, 8192), keepAlive: 15 * time.Second,
	}
	for _, o := range allowedOrigins {
		s.allowed[strings.TrimRight(o, "/")] = true
	}
	go s.pump()
	return s
}

func (s *Server) pump() {
	for ev := range s.events {
		b, _ := json.Marshal(ev)
		s.broadcast("key", b)
	}
}

func (s *Server) broadcast(event string, data []byte) {
	msg := []byte(fmt.Sprintf("event: %s\ndata: %s\n\n", event, data))
	s.mu.Lock()
	defer s.mu.Unlock()
	for c := range s.clients {
		select {
		case c <- msg:
		default:
			s.dropped++ // client too slow; counted and reported in status
		}
	}
}

func (s *Server) statusJSON() []byte {
	s.mu.Lock()
	defer s.mu.Unlock()
	kinds := []string{}
	for _, src := range s.sources {
		kinds = append(kinds, src.Kind())
	}
	st := map[string]any{
		"agent": "scanwise-agent", "version": s.version, "platform": runtime.GOOS + "/" + runtime.GOARCH,
		"sources": kinds, "selected": nil, "grab": false, "clients": len(s.clients), "dropped": s.dropped,
	}
	if s.sel != nil {
		st["selected"] = s.sel.device
		st["grab"] = s.sel.grab
	}
	b, _ := json.Marshal(st)
	return b
}

func isLoopbackHost(host string) bool {
	h, _, err := net.SplitHostPort(host)
	if err != nil {
		h = host
	}
	h = strings.Trim(h, "[]")
	if h == "localhost" {
		return true
	}
	ip := net.ParseIP(h)
	return ip != nil && ip.IsLoopback()
}

// guard applies Host/Origin checks and CORS (incl. Private Network Access) headers.
func (s *Server) guard(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if !isLoopbackHost(r.Host) {
			http.Error(w, "forbidden host", http.StatusForbidden)
			return
		}
		origin := strings.TrimRight(r.Header.Get("Origin"), "/")
		switch {
		case origin == "" && s.allowNoOrigin:
		case origin == "":
			http.Error(w, "missing Origin (use --allow-no-origin for command-line clients)", http.StatusForbidden)
			return
		case !s.allowed[origin]:
			http.Error(w, "origin not allowed: "+origin+" (start the agent with --allow-origin "+origin+")", http.StatusForbidden)
			return
		default:
			w.Header().Set("Access-Control-Allow-Origin", origin)
			w.Header().Set("Vary", "Origin")
		}
		if r.Method == http.MethodOptions {
			w.Header().Set("Access-Control-Allow-Methods", "GET, POST")
			w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
			if r.Header.Get("Access-Control-Request-Private-Network") == "true" {
				w.Header().Set("Access-Control-Allow-Private-Network", "true")
			}
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next(w, r)
	}
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	if b, ok := v.([]byte); ok {
		w.Write(b)
		return
	}
	json.NewEncoder(w).Encode(v)
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/status", s.guard(func(w http.ResponseWriter, r *http.Request) { writeJSON(w, 200, s.statusJSON()) }))
	mux.HandleFunc("/devices", s.guard(s.handleDevices))
	mux.HandleFunc("/select", s.guard(s.handleSelect))
	mux.HandleFunc("/release", s.guard(s.handleRelease))
	mux.HandleFunc("/events", s.guard(s.handleEvents))
	return mux
}

func (s *Server) handleDevices(w http.ResponseWriter, r *http.Request) {
	all := []Device{}
	errs := []string{}
	for _, src := range s.sources {
		ds, err := src.Devices()
		if err != nil {
			errs = append(errs, src.Kind()+": "+err.Error())
		}
		all = append(all, ds...)
	}
	writeJSON(w, 200, map[string]any{"devices": all, "errors": errs})
}

func (s *Server) sourceFor(id string) Source {
	kind, _, _ := strings.Cut(id, ":")
	for _, src := range s.sources {
		if src.Kind() == kind {
			return src
		}
	}
	return nil
}

func (s *Server) release() {
	s.mu.Lock()
	sel := s.sel
	s.sel = nil
	s.mu.Unlock()
	if sel != nil {
		sel.stop()
	}
}

func (s *Server) handleSelect(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "POST only", http.StatusMethodNotAllowed)
		return
	}
	var req struct {
		ID   string `json:"id"`
		Grab bool   `json:"grab"`
	}
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096)).Decode(&req); err != nil || req.ID == "" {
		writeJSON(w, 400, map[string]string{"error": "body must be {\"id\": \"...\", \"grab\": bool}"})
		return
	}
	if err := s.Select(req.ID, req.Grab); err != nil {
		writeJSON(w, 400, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, 200, s.statusJSON())
}

// Select opens a device (closing any previous one).
func (s *Server) Select(id string, grab bool) error {
	s.selectMu.Lock()
	defer s.selectMu.Unlock()
	src := s.sourceFor(id)
	if src == nil {
		return fmt.Errorf("no source for device %q", id)
	}
	var dev Device
	ds, _ := src.Devices()
	for _, d := range ds {
		if d.ID == id {
			dev = d
		}
	}
	if dev.ID == "" {
		return fmt.Errorf("device %q not found", id)
	}
	if grab && !dev.CanGrab {
		return fmt.Errorf("device %q cannot be grabbed on this platform", id)
	}
	s.release()
	stop, err := src.Open(id, grab, s.events)
	if err != nil {
		return err
	}
	s.mu.Lock()
	s.sel = &selection{device: dev, grab: grab, stop: stop}
	s.mu.Unlock()
	s.broadcast("status", s.statusJSON())
	return nil
}

func (s *Server) handleRelease(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "POST only", http.StatusMethodNotAllowed)
		return
	}
	s.selectMu.Lock()
	s.release()
	s.selectMu.Unlock()
	s.broadcast("status", s.statusJSON())
	writeJSON(w, 200, s.statusJSON())
}

func (s *Server) handleEvents(w http.ResponseWriter, r *http.Request) {
	fl, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "streaming unsupported", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	c := make(chan []byte, 4096)
	s.mu.Lock()
	s.clients[c] = struct{}{}
	s.mu.Unlock()
	defer func() {
		s.mu.Lock()
		delete(s.clients, c)
		s.mu.Unlock()
	}()
	fmt.Fprintf(w, "retry: 2000\n\nevent: status\ndata: %s\n\n", s.statusJSON())
	fl.Flush()
	tick := time.NewTicker(s.keepAlive)
	defer tick.Stop()
	for {
		select {
		case <-r.Context().Done():
			return
		case msg := <-c:
			w.Write(msg)
			// Drain whatever else is queued before flushing: one flush per burst.
			for n := len(c); n > 0; n-- {
				w.Write(<-c)
			}
			fl.Flush()
		case <-tick.C:
			fmt.Fprint(w, ": keepalive\n\n")
			fl.Flush()
		}
	}
}
