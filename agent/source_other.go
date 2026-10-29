//go:build !linux && !windows

package main

// No native capture on this platform yet; the replay source still works.
func newNativeSource() Source { return nil }
