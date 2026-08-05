package io.docmeta.worker;

import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.IOException;
import java.net.URI;
import java.net.Socket;
import java.net.URL;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import org.junit.jupiter.api.Test;

final class NetworkAccessDenyTest {
    @Test
    void blocksCommonRemoteUrlProtocolsBeforeAConnectionIsCreated() throws Exception {
        NetworkAccessDeny.install();
        URL url = URI.create("https://127.0.0.1:9/should-not-connect").toURL();

        assertThrows(IOException.class, url::openConnection);
        assertThrows(SecurityException.class, () -> new Socket("127.0.0.1", 9));

        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder(url.toURI()).GET().build();
        assertThrows(SecurityException.class, () -> client.send(
                request,
                java.net.http.HttpResponse.BodyHandlers.discarding()));
    }
}
