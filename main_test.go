package main

import (
	"bytes"
	"encoding/json"
	"io"
	"log/slog"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

const validPDF = "%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"

func newTestHandler(maxUploadBytes int64) http.Handler {
	return newHandler(maxUploadBytes, slog.New(slog.NewTextHandler(io.Discard, nil)))
}

func newUploadRequest(t *testing.T, fieldName, filename string, content []byte) *http.Request {
	t.Helper()

	var body bytes.Buffer
	writer := multipart.NewWriter(&body)

	part, err := writer.CreateFormFile(fieldName, filename)
	if err != nil {
		t.Fatalf("create form file: %v", err)
	}

	if _, err := part.Write(content); err != nil {
		t.Fatalf("write form file: %v", err)
	}

	if err := writer.Close(); err != nil {
		t.Fatalf("close multipart writer: %v", err)
	}

	req := httptest.NewRequest(http.MethodPost, "/extract", &body)
	req.Header.Set("Content-Type", writer.FormDataContentType())

	return req
}

func serve(handler http.Handler, req *http.Request) *httptest.ResponseRecorder {
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	return rec
}

func TestHealth(t *testing.T) {
	rec := serve(newTestHandler(defaultMaxUploadBytes), httptest.NewRequest(http.MethodGet, "/health", nil))

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d", http.StatusOK, rec.Code)
	}

	if got := rec.Header().Get("Content-Type"); !strings.HasPrefix(got, "application/json") {
		t.Fatalf("expected JSON content type, got %q", got)
	}

	var body healthResponse
	if err := json.NewDecoder(rec.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}

	if body.Status != "ok" {
		t.Fatalf("expected status ok, got %q", body.Status)
	}
}

func TestHealthRejectsWrongMethod(t *testing.T) {
	rec := serve(newTestHandler(defaultMaxUploadBytes), httptest.NewRequest(http.MethodPost, "/health", nil))

	if rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf("expected status %d, got %d", http.StatusMethodNotAllowed, rec.Code)
	}

	if got := rec.Header().Get("Allow"); got != http.MethodGet {
		t.Fatalf("expected Allow header %q, got %q", http.MethodGet, got)
	}
}

func TestExtractAcceptsValidPDF(t *testing.T) {
	req := newUploadRequest(t, "file", "document.pdf", []byte(validPDF))
	rec := serve(newTestHandler(defaultMaxUploadBytes), req)

	if rec.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, rec.Code, rec.Body.String())
	}

	var body extractResponse
	if err := json.NewDecoder(rec.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}

	if body.Status != "accepted" {
		t.Fatalf("expected status accepted, got %q", body.Status)
	}

	if body.Filename != "document.pdf" {
		t.Fatalf("expected filename document.pdf, got %q", body.Filename)
	}

	if body.Size != int64(len(validPDF)) {
		t.Fatalf("expected size %d, got %d", len(validPDF), body.Size)
	}
}

func TestExtractRejectsMissingFileField(t *testing.T) {
	req := newUploadRequest(t, "document", "document.pdf", []byte(validPDF))
	rec := serve(newTestHandler(defaultMaxUploadBytes), req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected status %d, got %d", http.StatusBadRequest, rec.Code)
	}
}

func TestExtractRejectsNonPDF(t *testing.T) {
	req := newUploadRequest(t, "file", "document.txt", []byte("this is not a pdf"))
	rec := serve(newTestHandler(defaultMaxUploadBytes), req)

	if rec.Code != http.StatusUnsupportedMediaType {
		t.Fatalf("expected status %d, got %d", http.StatusUnsupportedMediaType, rec.Code)
	}
}

func TestExtractRejectsEmptyFile(t *testing.T) {
	req := newUploadRequest(t, "file", "document.pdf", nil)
	rec := serve(newTestHandler(defaultMaxUploadBytes), req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected status %d, got %d", http.StatusBadRequest, rec.Code)
	}
}

func TestExtractRejectsOversizedFile(t *testing.T) {
	content := append([]byte(pdfMagic), bytes.Repeat([]byte("a"), 256)...)
	req := newUploadRequest(t, "file", "document.pdf", content)
	rec := serve(newTestHandler(128), req)

	if rec.Code != http.StatusRequestEntityTooLarge {
		t.Fatalf("expected status %d, got %d", http.StatusRequestEntityTooLarge, rec.Code)
	}
}

func TestExtractRejectsWrongMethod(t *testing.T) {
	rec := serve(newTestHandler(defaultMaxUploadBytes), httptest.NewRequest(http.MethodGet, "/extract", nil))

	if rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf("expected status %d, got %d", http.StatusMethodNotAllowed, rec.Code)
	}

	if got := rec.Header().Get("Allow"); got != http.MethodPost {
		t.Fatalf("expected Allow header %q, got %q", http.MethodPost, got)
	}
}

func TestExtractRejectsMalformedMultipart(t *testing.T) {
	req := httptest.NewRequest(http.MethodPost, "/extract", strings.NewReader("not a multipart body"))
	rec := serve(newTestHandler(defaultMaxUploadBytes), req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected status %d, got %d", http.StatusBadRequest, rec.Code)
	}
}
