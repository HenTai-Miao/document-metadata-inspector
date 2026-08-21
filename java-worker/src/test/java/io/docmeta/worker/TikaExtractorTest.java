package io.docmeta.worker;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.ByteArrayInputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.HexFormat;
import java.util.List;
import java.security.MessageDigest;
import org.apache.poi.util.Units;
import org.apache.poi.xwpf.usermodel.Document;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDDocumentInformation;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.poi.xwpf.usermodel.XWPFDocument;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

final class TikaExtractorTest {
    private static final String ONE_PIXEL_PNG =
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII=";

    @TempDir
    Path temporaryDirectory;

    @Test
    void extractsPdfMetadataWithoutReturningBodyText() throws Exception {
        Path path = temporaryDirectory.resolve("sample.pdf");
        try (PDDocument document = new PDDocument()) {
            document.addPage(new PDPage());
            PDDocumentInformation info = new PDDocumentInformation();
            info.setAuthor("Alice PDFBox");
            info.setTitle("Controlled PDF");
            document.setDocumentInformation(info);
            document.save(path.toFile());
        }

        Protocol.Response response = new TikaExtractor().extract(request(path));

        assertEquals("ok", response.status());
        assertEquals("application/pdf", response.contentType());
        assertTrue(
                flatten(response, "creator").contains("Alice PDFBox"),
                () -> "Actual metadata: " + response.metadata());
        assertTrue(
                response.metadata().keySet().stream()
                        .noneMatch(name -> name.endsWith("X-TIKA:parse_time_millis")),
                () -> "Runtime timing leaked into metadata: " + response.metadata());
        assertTrue(
                !response.metadata().containsKey("resourceName"),
                () -> "Staged resource name leaked into metadata: " + response.metadata());
    }

    @Test
    void extractsDocxCoreProperties() throws Exception {
        Path path = temporaryDirectory.resolve("sample.docx");
        try (XWPFDocument document = new XWPFDocument()) {
            document.getProperties().getCoreProperties().setCreator("Alice POI");
            try (var output = Files.newOutputStream(path)) {
                document.write(output);
            }
        }

        Protocol.Response response = new TikaExtractor().extract(request(path));

        assertEquals("ok", response.status());
        assertTrue(response.contentType().contains("wordprocessingml"));
        assertTrue(flatten(response, "creator").contains("Alice POI"));
    }

    @Test
    void excludesTemporaryFileMetadataForEmbeddedImages() throws Exception {
        Path path = temporaryDirectory.resolve("embedded.docx");
        byte[] image = Base64.getDecoder().decode(ONE_PIXEL_PNG);
        try (XWPFDocument document = new XWPFDocument();
                ByteArrayInputStream input = new ByteArrayInputStream(image)) {
            document.createParagraph()
                    .createRun()
                    .addPicture(
                            input,
                            Document.PICTURE_TYPE_PNG,
                            "original.png",
                            Units.toEMU(1),
                            Units.toEMU(1));
            try (var output = Files.newOutputStream(path)) {
                document.write(output);
            }
        }

        Protocol.Response response = new TikaExtractor().extract(request(path));

        assertEquals("ok", response.status());
        assertTrue(!response.embeddedResources().isEmpty());
        Protocol.EmbeddedResource embedded = response.embeddedResources().getFirst();
        assertEquals(image.length, embedded.sizeBytes());
        assertEquals(
                HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(image)),
                embedded.sha256());
        assertEquals("c".repeat(64), embedded.parentId());
        assertEquals(1, embedded.depth());
        assertEquals(64, embedded.resourceId().length());
        assertTrue(
                response.metadata().keySet().stream()
                        .noneMatch(
                                name ->
                                        name.endsWith(".File Name")
                                                || name.endsWith(".File Modified Date")),
                () -> "Temporary embedded metadata leaked: " + response.metadata());
    }

    @Test
    void rejectsEmbeddedContentBeyondTheTotalByteBudget() throws Exception {
        Path path = temporaryDirectory.resolve("embedded-limit.docx");
        byte[] image = Base64.getDecoder().decode(ONE_PIXEL_PNG);
        try (XWPFDocument document = new XWPFDocument();
                ByteArrayInputStream input = new ByteArrayInputStream(image)) {
            document.createParagraph()
                    .createRun()
                    .addPicture(
                            input,
                            Document.PICTURE_TYPE_PNG,
                            "original.png",
                            Units.toEMU(1),
                            Units.toEMU(1));
            try (var output = Files.newOutputStream(path)) {
                document.write(output);
            }
        }

        Protocol.Request request = new Protocol.Request(
                "test-request",
                path.toString(),
                "c".repeat(64),
                null,
                new ResourceLimits(2_000_000, 3, 100, 10));

        Protocol.Response response = new TikaExtractor().extract(request);

        assertEquals("failed", response.status());
        assertEquals("resource_limit_exceeded", response.error().code());
    }

    @Test
    void rejectsMetadataWhileBuildingAnOversizedResponse() throws Exception {
        Path path = temporaryDirectory.resolve("large-metadata.pdf");
        try (PDDocument document = new PDDocument()) {
            document.addPage(new PDPage());
            PDDocumentInformation info = new PDDocumentInformation();
            info.setAuthor("x".repeat(20_000));
            document.setDocumentInformation(info);
            document.save(path.toFile());
        }
        Protocol.Request request = new Protocol.Request(
                "test-request",
                path.toString(),
                "c".repeat(64),
                null,
                new ResourceLimits(2048, 3, 100, 2_000_000));

        Protocol.Response response = new TikaExtractor().extract(request);

        assertEquals("failed", response.status());
        assertEquals("resource_limit_exceeded", response.error().code());
    }

    private static Protocol.Request request(Path path) {
        return new Protocol.Request(
                "test-request",
                path.toString(),
                "c".repeat(64),
                null,
                new ResourceLimits(2_000_000, 3, 100, 2_000_000));
    }

    private static List<String> flatten(Protocol.Response response, String fragment) {
        return response.metadata().entrySet().stream()
                .filter(entry -> entry.getKey().toLowerCase().contains(fragment.toLowerCase()))
                .flatMap(entry -> entry.getValue().stream())
                .toList();
    }
}
