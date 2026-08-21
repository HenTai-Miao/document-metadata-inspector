package io.docmeta.worker;

import java.io.IOException;
import java.net.InetAddress;
import java.net.URL;
import java.net.URLConnection;
import java.net.URLStreamHandler;
import java.security.Permission;
import java.util.Set;

final class NetworkAccessDeny {
    private static final Set<String> BLOCKED_PROTOCOLS =
            Set.of("http", "https", "ftp", "gopher", "ldap", "ldaps");
    private static boolean installed;

    private NetworkAccessDeny() {}

    @SuppressWarnings("removal")
    static synchronized void install() {
        if (installed) {
            return;
        }
        URL.setURLStreamHandlerFactory(protocol -> {
            if (!BLOCKED_PROTOCOLS.contains(protocol.toLowerCase())) {
                return null;
            }
            return new URLStreamHandler() {
                @Override
                protected URLConnection openConnection(URL url) throws IOException {
                    throw new IOException("document parser network access is disabled");
                }
            };
        });
        System.setSecurityManager(new NoNetworkSecurityManager());
        installed = true;
    }

    @SuppressWarnings("removal")
    private static final class NoNetworkSecurityManager extends SecurityManager {
        @Override
        public void checkPermission(Permission permission) {
            // The worker keeps ordinary local JVM permissions and denies every
            // network entry point through the dedicated checks below.
        }

        @Override
        public void checkConnect(String host, int port) {
            throw denied();
        }

        @Override
        public void checkConnect(String host, int port, Object context) {
            throw denied();
        }

        @Override
        public void checkListen(int port) {
            throw denied();
        }

        @Override
        public void checkAccept(String host, int port) {
            throw denied();
        }

        @Override
        public void checkMulticast(InetAddress address) {
            throw denied();
        }

        private static SecurityException denied() {
            return new SecurityException("document parser network access is disabled");
        }
    }
}
