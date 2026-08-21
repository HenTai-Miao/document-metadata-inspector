package io.docmeta.worker;

import com.fasterxml.jackson.core.JsonProcessingException;
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;

public final class Main {
    private static final int MAX_REQUEST_CHARACTERS = 1_048_576;

    private Main() {}

    public static void main(String[] args) throws IOException {
        NetworkAccessDeny.install();
        TikaExtractor extractor = new TikaExtractor();
        try (BufferedReader input = new BufferedReader(
                        new InputStreamReader(System.in, StandardCharsets.UTF_8));
                BufferedWriter output = new BufferedWriter(
                        new OutputStreamWriter(System.out, StandardCharsets.UTF_8))) {
            String line;
            while ((line = input.readLine()) != null) {
                Protocol.Response response = processLine(line, extractor);
                output.write(Protocol.writeResponse(response));
                output.newLine();
                output.flush();
            }
        }
    }

    private static Protocol.Response processLine(String line, TikaExtractor extractor) {
        if (line.length() > MAX_REQUEST_CHARACTERS) {
            return Protocol.Response.failure("invalid", "invalid_request");
        }
        try {
            Protocol.Request request = Protocol.readRequest(line);
            return extractor.extract(request);
        } catch (JsonProcessingException | IllegalArgumentException exception) {
            return Protocol.Response.failure("invalid", "invalid_request");
        } catch (RuntimeException exception) {
            return Protocol.Response.failure("invalid", "parser_crashed");
        }
    }
}
