package main

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"time"
)

const defaultURL = "http://127.0.0.1:3200/ready"

func main() {
	url := os.Getenv("TEMPO_HEALTHCHECK_URL")
	if url == "" {
		url = defaultURL
	}

	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Get(url) // #nosec G107 -- URL is an operator-controlled local readiness endpoint.
	if err != nil {
		fmt.Fprintf(os.Stderr, "tempo readiness request failed: %v\n", err)
		os.Exit(1)
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, 4096))

	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		fmt.Fprintf(os.Stderr, "tempo readiness returned HTTP %d\n", resp.StatusCode)
		os.Exit(1)
	}
}
