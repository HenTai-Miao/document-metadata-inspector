package io.docmeta.worker;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

final class Protocol {
    private static final ObjectMapper MAPPER = new ObjectMapper()
            .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
            .setSerializationInclusion(JsonInclude.Include.NON_NULL)
            .enable(com.fasterxml.jackson.databind.DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

    private Protocol() {}

    static Request readRequest(String json) throws JsonProcessingException {
        return MAPPER.readValue(json, Request.class);
    }

    static Response readResponse(String json) throws JsonProcessingException {
        return MAPPER.readValue(json, Response.class);
    }

    static String writeResponse(Response response) throws JsonProcessingException {
        return MAPPER.writeValueAsString(response);
    }

    record Request(
            String requestId,
            String path,
            String sourceSha256,
            String passwordToken,
            ResourceLimits limits) {
        Request {
            if (requestId == null || requestId.isBlank()) {
                throw new IllegalArgumentException("request_id is required");
            }
            if (path == null || path.isBlank()) {
                throw new IllegalArgumentException("path is required");
            }
            requireSha256(sourceSha256, "source_sha256");
            Objects.requireNonNull(limits, "limits is required");
        }
    }

    record EmbeddedResource(
            String resourceId,
            String parentId,
            int depth,
            String path,
            String contentType,
            long sizeBytes,
            String sha256) {
        EmbeddedResource {
            requireSha256(resourceId, "resource_id");
            requireSha256(parentId, "parent_id");
            requireSha256(sha256, "sha256");
            if (depth <= 0) {
                throw new IllegalArgumentException("depth must be positive");
            }
            path = path == null || path.isBlank() ? "unnamed" : path;
            contentType = contentType == null || contentType.isBlank()
                    ? "application/octet-stream"
                    : contentType;
            if (sizeBytes < -1) {
                throw new IllegalArgumentException("size_bytes must be -1 or greater");
            }
        }
    }

    private static void requireSha256(String value, String name) {
        if (value == null || !value.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException(name + " must be a lowercase SHA-256");
        }
    }

    record ErrorInfo(String code, String message) {
        ErrorInfo {
            Objects.requireNonNull(code, "error code is required");
            Objects.requireNonNull(message, "error message is required");
        }
    }

    record Response(
            String requestId,
            String status,
            String contentType,
            Map<String, List<String>> metadata,
            List<EmbeddedResource> embeddedResources,
            List<String> warnings,
            ErrorInfo error) {
        Response {
            if (requestId == null || requestId.isBlank()) {
                throw new IllegalArgumentException("request_id is required");
            }
            if (status == null || status.isBlank()) {
                throw new IllegalArgumentException("status is required");
            }
            metadata = immutableMetadata(metadata);
            embeddedResources = List.copyOf(
                    embeddedResources == null ? List.of() : embeddedResources);
            warnings = List.copyOf(warnings == null ? List.of() : warnings);
        }

        static Response success(
                String requestId,
                String contentType,
                Map<String, List<String>> metadata,
                List<EmbeddedResource> embeddedResources,
                List<String> warnings) {
            return new Response(
                    requestId,
                    warnings == null || warnings.isEmpty() ? "ok" : "partial",
                    contentType,
                    metadata,
                    embeddedResources,
                    warnings,
                    null);
        }

        static Response failure(String requestId, String code) {
            return new Response(
                    requestId,
                    "failed",
                    null,
                    Map.of(),
                    List.of(),
                    List.of(),
                    new ErrorInfo(code, fixedErrorMessage(code)));
        }

        private static Map<String, List<String>> immutableMetadata(
                Map<String, List<String>> source) {
            if (source == null || source.isEmpty()) {
                return Map.of();
            }
            Map<String, List<String>> copy = new LinkedHashMap<>();
            source.forEach((key, values) -> {
                if (key == null || key.isBlank()) {
                    throw new IllegalArgumentException("metadata keys must not be blank");
                }
                List<String> safeValues = new ArrayList<>();
                if (values != null) {
                    values.stream().filter(Objects::nonNull).forEach(safeValues::add);
                }
                copy.put(key, List.copyOf(safeValues));
            });
            return Collections.unmodifiableMap(copy);
        }

        private static String fixedErrorMessage(String code) {
            return switch (code) {
                case "invalid_request" -> "The Apache worker request was invalid.";
                case "parser_unavailable" -> "The Apache metadata parser is unavailable.";
                case "password_required" -> "This document requires a password.";
                case "wrong_password" -> "The supplied document password was not accepted.";
                case "resource_limit_exceeded" -> "The Apache parser reached a resource limit.";
                case "parser_timeout" -> "The Apache metadata parser timed out.";
                default -> "The Apache metadata parser failed.";
            };
        }
    }
}
