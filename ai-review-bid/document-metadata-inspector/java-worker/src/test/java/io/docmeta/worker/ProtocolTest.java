package io.docmeta.worker;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.core.JsonProcessingException;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

final class ProtocolTest {
    @Test
    void requestRoundTripsAndUnknownFieldsAreRejected() throws Exception {
        String json = """
                {"request_id":"req-1","path":"/tmp/source.docx",
                 "source_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
                 "password_token":"memory-only",
                 "limits":{"max_output_bytes":1000000,
                           "max_embedded_depth":3,
                           "max_embedded_resources":100,
                           "max_embedded_total_bytes":2000000}}
                """;

        Protocol.Request request = Protocol.readRequest(json);

        assertEquals("req-1", request.requestId());
        assertEquals("/tmp/source.docx", request.path());
        assertEquals("memory-only", request.passwordToken());
        assertEquals(3, request.limits().maxEmbeddedDepth());

        String unknown = json.replace("\"request_id\"", "\"unknown\":1,\"request_id\"");
        assertThrows(JsonProcessingException.class, () -> Protocol.readRequest(unknown));
    }

    @Test
    void duplicateMetadataValuesRemainArraysAndPasswordsNeverSerialize() throws Exception {
        Protocol.Response response = Protocol.Response.success(
                "req-2",
                "application/pdf",
                Map.of("Author", List.of("Alice", "ALICE")),
                List.of(new Protocol.EmbeddedResource(
                        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                        "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
                        1,
                        "attachment.txt",
                        "text/plain",
                        12L,
                        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")),
                List.of());

        String json = Protocol.writeResponse(response);

        assertTrue(json.contains("\"Author\":[\"Alice\",\"ALICE\"]"));
        assertFalse(json.contains("password"));
        assertEquals("req-2", Protocol.readResponse(json).requestId());
    }

    @Test
    void failureMessagesAreFixedAndContainNoAbsolutePathOrPassword() throws Exception {
        Protocol.Response response = Protocol.Response.failure("req-3", "parser_crashed");

        String json = Protocol.writeResponse(response);

        assertTrue(json.contains("The Apache metadata parser failed."));
        assertFalse(json.contains("/private/tmp/source.pdf"));
        assertFalse(json.contains("secret-value"));
    }
}
