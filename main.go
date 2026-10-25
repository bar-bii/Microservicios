package main

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"
)

const (
	defaultPort           = "8080"
	defaultMaxUploadBytes = 10 << 20
	pdfMagic              = "%PDF-"
	multipartOverhead     = 1 << 20
	shutdownTimeout       = 10 * time.Second
)

type app struct {
	maxUploadBytes int64
	logger         *slog.Logger
}

type healthResponse struct {
	Status string `json:"status"`
}

type extractResponse struct {
	Status   string `json:"status"`
	Filename string `json:"filename"`
	Size     int64  `json:"size"`
}

type errorResponse struct {
	Error string `json:"error"`
}

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	port := envOrDefault("PORT", defaultPort)
	maxUploadBytes := envInt64("MAX_UPLOAD_BYTES", defaultMaxUploadBytes)

	srv := &http.Server{
		Addr:              ":" + port,
		Handler:           newHandler(maxUploadBytes, logger),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       30 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	serverErr := make(chan error, 1)
	go func() {
		logger.Info("server starting", "addr", srv.Addr)
		serverErr <- srv.ListenAndServe()
	}()

	select {
	case err := <-serverErr:
		if err != nil && !errors.Is(err, http.ErrServerClosed) {
			logger.Error("server failed", "error", err)
			os.Exit(1)
		}
	case <-ctx.Done():
		logger.Info("shutdown signal received")

		shutdownCtx, cancel := context.WithTimeout(context.Background(), shutdownTimeout)
		defer cancel()

		if err := srv.Shutdown(shutdownCtx); err != nil {
			logger.Error("graceful shutdown failed", "error", err)
			os.Exit(1)
		}

		if err := <-serverErr; err != nil && !errors.Is(err, http.ErrServerClosed) {
			logger.Error("server failed during shutdown", "error", err)
			os.Exit(1)
		}

		logger.Info("server stopped")
	}
}

func newHandler(maxUploadBytes int64, logger *slog.Logger) http.Handler {
	a := &app{
		maxUploadBytes: maxUploadBytes,
		logger:         logger,
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", a.handleHealth)
	mux.HandleFunc("/extract", a.handleExtract)

	return mux
}

func (a *app) handleHealth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", http.MethodGet)
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	writeJSON(w, http.StatusOK, healthResponse{Status: "ok"})
}

func (a *app) handleExtract(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", http.MethodPost)
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	r.Body = http.MaxBytesReader(w, r.Body, a.maxUploadBytes+multipartOverhead)

	if err := r.ParseMultipartForm(a.maxUploadBytes); err != nil {
		var maxBytesErr *http.MaxBytesError
		if errors.As(err, &maxBytesErr) {
			writeError(w, http.StatusRequestEntityTooLarge, "uploaded file is too large")
			return
		}
		writeError(w, http.StatusBadRequest, "invalid multipart form")
		return
	}

	if r.MultipartForm != nil {
		defer r.MultipartForm.RemoveAll()
	}

	file, header, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, "missing file field 'file'")
		return
	}
	defer file.Close()

	if header.Size == 0 {
		writeError(w, http.StatusBadRequest, "uploaded file is empty")
		return
	}

	if header.Size > a.maxUploadBytes {
		writeError(w, http.StatusRequestEntityTooLarge, "uploaded file is too large")
		return
	}

	magic := make([]byte, len(pdfMagic))
	n, err := io.ReadFull(file, magic)
	if err != nil || string(magic[:n]) != pdfMagic {
		writeError(w, http.StatusUnsupportedMediaType, "uploaded file is not a valid PDF")
		return
	}

	a.logger.Info("pdf received",
		"filename", header.Filename,
		"size", header.Size,
	)

	writeJSON(w, http.StatusAccepted, extractResponse{
		Status:   "accepted",
		Filename: header.Filename,
		Size:     header.Size,
	})
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(payload); err != nil {
		slog.Error("failed to encode JSON response", "error", err)
	}
}

func writeError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, errorResponse{Error: message})
}

func envOrDefault(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func envInt64(key string, fallback int64) int64 {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}

	parsed, err := strconv.ParseInt(value, 10, 64)
	if err != nil || parsed <= 0 {
		slog.Warn("invalid integer environment variable, using default",
			"key", key,
			"value", value,
			"default", fallback,
		)
		return fallback
	}

	return parsed
}
