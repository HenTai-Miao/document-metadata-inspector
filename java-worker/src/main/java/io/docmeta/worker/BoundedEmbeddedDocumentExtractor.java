package io.docmeta.worker;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.HexFormat;
import org.apache.tika.extractor.EmbeddedDocumentExtractor;
import org.apache.tika.extractor.ParsingEmbeddedDocumentExtractor;
import org.apache.tika.metadata.Metadata;
import org.apache.tika.metadata.TikaCoreProperties;
import org.apache.tika.parser.ParseContext;
import org.xml.sax.ContentHandler;
import org.xml.sax.SAXException;

final class BoundedEmbeddedDocumentExtractor implements EmbeddedDocumentExtractor {
    static final String RESOURCE_ID = "docmeta:embedded_resource_id";
    static final String PARENT_ID = "docmeta:embedded_parent_id";
    static final String DEPTH = "docmeta:embedded_depth";
    static final String SHA256 = "docmeta:embedded_sha256";
    static final String SIZE = "docmeta:embedded_size";

    private static final int BUFFER_BYTES = 64 * 1024;

    private final ParsingEmbeddedDocumentExtractor delegate;
    private final Path temporaryDirectory;
    private final long maxTotalBytes;
    private final Deque<String> parentIds = new ArrayDeque<>();
    private long totalBytes;
    private long ordinal;
    private boolean byteLimitExceeded;

    BoundedEmbeddedDocumentExtractor(
            ParseContext context,
            Path temporaryDirectory,
            String sourceSha256,
            long maxTotalBytes) {
        this.delegate = new ParsingEmbeddedDocumentExtractor(context);
        this.temporaryDirectory = temporaryDirectory;
        this.maxTotalBytes = maxTotalBytes;
        this.parentIds.push(sourceSha256);
    }

    @Override
    public boolean shouldParseEmbedded(Metadata metadata) {
        return delegate.shouldParseEmbedded(metadata);
    }

    @Override
    public void parseEmbedded(
            InputStream stream,
            ContentHandler handler,
            Metadata metadata,
            boolean outputHtml)
            throws SAXException, IOException {
        ordinal++;
        String resourcePath = firstNonBlank(
                metadata.get(TikaCoreProperties.FINAL_EMBEDDED_RESOURCE_PATH),
                metadata.get(TikaCoreProperties.EMBEDDED_RESOURCE_PATH),
                metadata.get(TikaCoreProperties.RESOURCE_NAME_KEY),
                "embedded-" + ordinal);
        Path staged = Files.createTempFile(temporaryDirectory, ".embedded-", ".bin");
        MessageDigest digest = sha256Digest();
        long size = 0L;
        try {
            try (OutputStream output = Files.newOutputStream(staged)) {
                byte[] buffer = new byte[BUFFER_BYTES];
                int read;
                while ((read = stream.read(buffer)) != -1) {
                    if (read == 0) {
                        continue;
                    }
                    if (read > maxTotalBytes - totalBytes) {
                        byteLimitExceeded = true;
                        throw new EmbeddedByteLimitException();
                    }
                    output.write(buffer, 0, read);
                    digest.update(buffer, 0, read);
                    totalBytes += read;
                    size += read;
                }
            }

            String contentSha256 = HexFormat.of().formatHex(digest.digest());
            String parentId = parentIds.getFirst();
            int depth = parentIds.size();
            String resourceId = resourceId(parentId, resourcePath, contentSha256);
            metadata.set(RESOURCE_ID, resourceId);
            metadata.set(PARENT_ID, parentId);
            metadata.set(DEPTH, Integer.toString(depth));
            metadata.set(SHA256, contentSha256);
            metadata.set(SIZE, Long.toString(size));

            parentIds.push(resourceId);
            try (InputStream stagedInput = Files.newInputStream(staged)) {
                delegate.parseEmbedded(stagedInput, handler, metadata, outputHtml);
            } finally {
                parentIds.pop();
            }
        } finally {
            Files.deleteIfExists(staged);
        }
    }

    boolean hasExceededByteLimit() {
        return byteLimitExceeded;
    }

    private static MessageDigest sha256Digest() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
    }

    private static String resourceId(String parentId, String path, String contentSha256) {
        MessageDigest digest = sha256Digest();
        digest.update(parentId.getBytes(StandardCharsets.UTF_8));
        digest.update((byte) 0);
        digest.update(path.getBytes(StandardCharsets.UTF_8));
        digest.update((byte) 0);
        digest.update(contentSha256.getBytes(StandardCharsets.US_ASCII));
        return HexFormat.of().formatHex(digest.digest());
    }

    private static String firstNonBlank(String... candidates) {
        for (String candidate : candidates) {
            if (candidate != null && !candidate.isBlank()) {
                return candidate;
            }
        }
        return "unnamed";
    }

    static final class EmbeddedByteLimitException extends IOException {
        private static final long serialVersionUID = 1L;
    }
}
