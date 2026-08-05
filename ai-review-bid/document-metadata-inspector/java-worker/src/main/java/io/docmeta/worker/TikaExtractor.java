package io.docmeta.worker;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.apache.tika.exception.EncryptedDocumentException;
import org.apache.tika.exception.TikaException;
import org.apache.tika.extractor.EmbeddedDocumentExtractor;
import org.apache.tika.metadata.HttpHeaders;
import org.apache.tika.metadata.Metadata;
import org.apache.tika.metadata.TikaCoreProperties;
import org.apache.tika.parser.AutoDetectParser;
import org.apache.tika.parser.ParseContext;
import org.apache.tika.parser.Parser;
import org.apache.tika.parser.PasswordProvider;
import org.apache.tika.parser.RecursiveParserWrapper;
import org.apache.tika.sax.BasicContentHandlerFactory;
import org.apache.tika.sax.BasicContentHandlerFactory.HANDLER_TYPE;
import org.apache.tika.sax.RecursiveParserWrapperHandler;
import org.xml.sax.ContentHandler;
import org.xml.sax.SAXException;

final class TikaExtractor {
    Protocol.Response extract(Protocol.Request request) {
        Path path;
        try {
            path = Path.of(request.path()).toAbsolutePath().normalize();
        } catch (RuntimeException exception) {
            return Protocol.Response.failure(request.requestId(), "invalid_request");
        }

        if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS) || !Files.isReadable(path)) {
            return Protocol.Response.failure(request.requestId(), "invalid_request");
        }

        try {
            return parse(path, request);
        } catch (EncryptedDocumentException exception) {
            String code = request.passwordToken() == null ? "password_required" : "wrong_password";
            return Protocol.Response.failure(request.requestId(), code);
        } catch (EmbeddedDepthLimitException
                | BoundedEmbeddedDocumentExtractor.EmbeddedByteLimitException exception) {
            return Protocol.Response.failure(request.requestId(), "resource_limit_exceeded");
        } catch (IOException | SAXException | TikaException | RuntimeException exception) {
            if (hasCause(exception, EncryptedDocumentException.class)) {
                String code = request.passwordToken() == null ? "password_required" : "wrong_password";
                return Protocol.Response.failure(request.requestId(), code);
            }
            if (hasCause(exception, EmbeddedDepthLimitException.class)) {
                return Protocol.Response.failure(request.requestId(), "resource_limit_exceeded");
            }
            if (hasCause(
                    exception,
                    BoundedEmbeddedDocumentExtractor.EmbeddedByteLimitException.class)) {
                return Protocol.Response.failure(request.requestId(), "resource_limit_exceeded");
            }
            return Protocol.Response.failure(request.requestId(), "parser_crashed");
        }
    }

    private static Protocol.Response parse(Path path, Protocol.Request request)
            throws IOException, SAXException, TikaException, EmbeddedDepthLimitException {
        AutoDetectParser parser = new AutoDetectParser();
        RecursiveParserWrapper wrapper = new RecursiveParserWrapper(parser);
        ParseContext context = new ParseContext();
        context.set(Parser.class, parser);
        BoundedEmbeddedDocumentExtractor embeddedExtractor =
                new BoundedEmbeddedDocumentExtractor(
                        context,
                        path.getParent(),
                        request.sourceSha256(),
                        request.limits().maxEmbeddedTotalBytes());
        context.set(
                EmbeddedDocumentExtractor.class,
                embeddedExtractor);
        if (request.passwordToken() != null) {
            String password = request.passwordToken();
            context.set(PasswordProvider.class, ignoredMetadata -> password);
        }

        Metadata root = new Metadata();
        root.set(TikaCoreProperties.RESOURCE_NAME_KEY, path.getFileName().toString());
        BasicContentHandlerFactory handlerFactory =
                new BasicContentHandlerFactory(HANDLER_TYPE.IGNORE, -1);
        DepthLimitedHandler handler = new DepthLimitedHandler(
                handlerFactory,
                request.limits().maxEmbeddedResources(),
                request.limits().maxEmbeddedDepth());

        try (InputStream input = Files.newInputStream(path)) {
            wrapper.parse(input, handler, root, context);
        } catch (SAXException exception) {
            if (hasCause(exception, EmbeddedDepthLimitException.class)) {
                throw new EmbeddedDepthLimitException();
            }
            throw exception;
        } catch (IOException exception) {
            if (hasCause(
                    exception,
                    BoundedEmbeddedDocumentExtractor.EmbeddedByteLimitException.class)) {
                throw new BoundedEmbeddedDocumentExtractor.EmbeddedByteLimitException();
            }
            throw exception;
        }

        if (embeddedExtractor.hasExceededByteLimit()) {
            return Protocol.Response.failure(request.requestId(), "resource_limit_exceeded");
        }

        List<Metadata> documents = handler.getMetadataList();
        if (documents.isEmpty()) {
            documents = List.of(root);
        }

        Metadata rootMetadata = documents.getFirst();
        Map<String, List<String>> flattened =
                flattenMetadata(documents, request.limits().maxOutputBytes());
        if (flattened == null) {
            return Protocol.Response.failure(request.requestId(), "resource_limit_exceeded");
        }
        List<Protocol.EmbeddedResource> embedded = describeEmbedded(documents);
        List<String> warnings = new ArrayList<>();
        if (handler.hasHitMaximumEmbeddedResources()) {
            warnings.add("embedded_resource_limit_reached");
        }

        String contentType = rootMetadata.get(HttpHeaders.CONTENT_TYPE);
        if (contentType == null || contentType.isBlank()) {
            contentType = "application/octet-stream";
            warnings.add("content_type_unknown");
        }

        Protocol.Response response = Protocol.Response.success(
                request.requestId(), contentType, flattened, embedded, warnings);
        if (Protocol.writeResponse(response).getBytes(java.nio.charset.StandardCharsets.UTF_8).length
                > request.limits().maxOutputBytes()) {
            return Protocol.Response.failure(request.requestId(), "resource_limit_exceeded");
        }
        return response;
    }

    private static Map<String, List<String>> flattenMetadata(
            List<Metadata> documents, long maxOutputBytes) {
        Map<String, List<String>> result = new LinkedHashMap<>();
        long remaining = Math.max(0L, maxOutputBytes - 4096L);
        for (int index = 0; index < documents.size(); index++) {
            Metadata metadata = documents.get(index);
            String prefix = index == 0 ? "" : "embedded[" + (index - 1) + "].";
            boolean embedded = index > 0;
            List<String> names = Arrays.stream(metadata.names())
                    .sorted(Comparator.naturalOrder())
                    .filter(name -> !isRuntimeArtifact(embedded, name))
                    .toList();
            for (String name : names) {
                String outputName = prefix + name;
                long required = jsonStringBytes(outputName) + 4L;
                String[] values = metadata.getValues(name);
                for (String value : values) {
                    required += jsonStringBytes(value) + 1L;
                    if (required > remaining) {
                        return null;
                    }
                }
                remaining -= required;
                result.computeIfAbsent(outputName, ignored -> new ArrayList<>())
                        .addAll(Arrays.asList(values));
            }
        }
        return result;
    }

    private static long jsonStringBytes(String value) {
        long bytes = 2L;
        for (int index = 0; index < value.length(); index++) {
            char character = value.charAt(index);
            if (character == '"' || character == '\\' || character == '\b'
                    || character == '\f' || character == '\n' || character == '\r'
                    || character == '\t') {
                bytes += 2L;
            } else if (character < 0x20) {
                bytes += 6L;
            } else if (character < 0x80) {
                bytes += 1L;
            } else if (character < 0x800) {
                bytes += 2L;
            } else if (Character.isHighSurrogate(character)
                    && index + 1 < value.length()
                    && Character.isLowSurrogate(value.charAt(index + 1))) {
                bytes += 4L;
                index++;
            } else {
                bytes += 3L;
            }
        }
        return bytes;
    }

    private static boolean isRuntimeArtifact(boolean embedded, String name) {
        if (name.startsWith("docmeta:")) {
            return true;
        }
        if ("X-TIKA:parse_time_millis".equals(name)) {
            return true;
        }
        if (!embedded && TikaCoreProperties.RESOURCE_NAME_KEY.equals(name)) {
            return true;
        }
        return embedded && ("File Name".equals(name) || "File Modified Date".equals(name));
    }

    private static List<Protocol.EmbeddedResource> describeEmbedded(List<Metadata> documents) {
        if (documents.size() < 2) {
            return List.of();
        }
        List<Protocol.EmbeddedResource> result = new ArrayList<>();
        for (int index = 1; index < documents.size(); index++) {
            Metadata metadata = documents.get(index);
            String resourcePath = firstNonBlank(
                    metadata.get(TikaCoreProperties.FINAL_EMBEDDED_RESOURCE_PATH),
                    metadata.get(TikaCoreProperties.EMBEDDED_RESOURCE_PATH),
                    metadata.get(TikaCoreProperties.RESOURCE_NAME_KEY),
                    "embedded[" + (index - 1) + "]");
            String contentType = firstNonBlank(
                    metadata.get(HttpHeaders.CONTENT_TYPE), "application/octet-stream");
            long size = parseSize(firstNonBlank(
                    metadata.get(BoundedEmbeddedDocumentExtractor.SIZE),
                    metadata.get(HttpHeaders.CONTENT_LENGTH)));
            int depth = parseDepth(metadata.get(BoundedEmbeddedDocumentExtractor.DEPTH));
            result.add(new Protocol.EmbeddedResource(
                    metadata.get(BoundedEmbeddedDocumentExtractor.RESOURCE_ID),
                    metadata.get(BoundedEmbeddedDocumentExtractor.PARENT_ID),
                    depth,
                    resourcePath,
                    contentType,
                    size,
                    metadata.get(BoundedEmbeddedDocumentExtractor.SHA256)));
        }
        return List.copyOf(result);
    }

    private static String firstNonBlank(String... candidates) {
        for (String candidate : candidates) {
            if (candidate != null && !candidate.isBlank()) {
                return candidate;
            }
        }
        return "unnamed";
    }

    private static long parseSize(String value) {
        if (value == null) {
            return -1L;
        }
        try {
            long parsed = Long.parseLong(value);
            return parsed < 0 ? -1L : parsed;
        } catch (NumberFormatException exception) {
            return -1L;
        }
    }

    private static int parseDepth(String value) {
        if (value == null) {
            return 1;
        }
        try {
            int parsed = Integer.parseInt(value);
            return parsed <= 0 ? 1 : parsed;
        } catch (NumberFormatException exception) {
            return 1;
        }
    }

    private static boolean hasCause(Throwable exception, Class<? extends Throwable> type) {
        Throwable current = exception;
        while (current != null) {
            if (type.isInstance(current)) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }

    private static final class DepthLimitedHandler extends RecursiveParserWrapperHandler {
        private final int maxEmbeddedDepth;

        DepthLimitedHandler(
                BasicContentHandlerFactory factory,
                int maxEmbeddedResources,
                int maxEmbeddedDepth) {
            super(factory, maxEmbeddedResources);
            this.maxEmbeddedDepth = maxEmbeddedDepth;
        }

        @Override
        public void startEmbeddedDocument(ContentHandler handler, Metadata metadata)
                throws SAXException {
            super.startEmbeddedDocument(handler, metadata);
            Integer depth = metadata.getInt(TikaCoreProperties.EMBEDDED_DEPTH);
            if (depth != null && depth > maxEmbeddedDepth) {
                throw new SAXException(new EmbeddedDepthLimitException());
            }
        }
    }

    private static final class EmbeddedDepthLimitException extends Exception {
        private static final long serialVersionUID = 1L;
    }
}
