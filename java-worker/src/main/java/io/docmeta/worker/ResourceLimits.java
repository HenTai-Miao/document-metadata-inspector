package io.docmeta.worker;

record ResourceLimits(
        long maxOutputBytes,
        int maxEmbeddedDepth,
        int maxEmbeddedResources,
        long maxEmbeddedTotalBytes) {
    private static final long MAX_PROTOCOL_OUTPUT_BYTES = 64L * 1024L * 1024L;
    private static final int MAX_EMBEDDED_DEPTH = 99;
    private static final int MAX_EMBEDDED_RESOURCES = 100_000;
    private static final long MAX_EMBEDDED_TOTAL_BYTES = 2L * 1024L * 1024L * 1024L;

    ResourceLimits {
        if (maxOutputBytes <= 0 || maxOutputBytes > MAX_PROTOCOL_OUTPUT_BYTES) {
            throw new IllegalArgumentException("max_output_bytes is outside the allowed range");
        }
        if (maxEmbeddedDepth <= 0 || maxEmbeddedDepth > MAX_EMBEDDED_DEPTH) {
            throw new IllegalArgumentException("max_embedded_depth is outside the allowed range");
        }
        if (maxEmbeddedResources <= 0 || maxEmbeddedResources > MAX_EMBEDDED_RESOURCES) {
            throw new IllegalArgumentException("max_embedded_resources is outside the allowed range");
        }
        if (maxEmbeddedTotalBytes <= 0 || maxEmbeddedTotalBytes > MAX_EMBEDDED_TOTAL_BYTES) {
            throw new IllegalArgumentException(
                    "max_embedded_total_bytes is outside the allowed range");
        }
    }
}
