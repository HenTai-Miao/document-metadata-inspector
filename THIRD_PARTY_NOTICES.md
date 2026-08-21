# Third-Party Notices

Document Metadata Inspector combines the components below. Copyright remains
with each component's authors. The corresponding license and notice files are
retained inside the bundled runtime trees or dependency archives.

## Document parsing runtimes

- Eclipse Temurin / OpenJDK 21.0.12+8: GPL version 2 with the Classpath
  Exception. The complete JRE legal tree is bundled under
  `tools/packaged/<platform>/apache/jre/legal/`.
- Apache Tika 3.3.2, Apache POI 5.5.1 and Apache PDFBox 3.0.8, together with
  their shaded Java dependencies: primarily Apache License 2.0, with
  component-specific notices. Consolidated `META-INF/NOTICE` and
  `META-INF/DEPENDENCIES`, plus component-specific license resources, are
  retained in the Apache worker JAR.
- ExifTool 13.55: Perl Artistic License or GNU General Public License. Its
  upstream README is retained under the bundled ExifTool license directory.
- Perl 5.44.0: Perl Artistic License or GNU General Public License. The
  upstream `Artistic` and `Copying` files are retained in every bundled Unix
  ExifTool runtime. The official standalone Windows ExifTool distribution
  retains its own license files.
- Archive::Zip 1.68: the same terms as Perl 5. Its upstream license/readme is
  retained in every bundled Unix ExifTool runtime.

## Python application dependencies

- cryptography 50.0.0: Apache-2.0 or BSD-3-Clause
- defusedxml 0.7.1: Python Software Foundation License
- FastAPI 0.141.1: MIT
- olefile 0.47: BSD
- openpyxl 3.1.5: MIT
- Pydantic 2.13.4: MIT
- pypdf 6.14.2: BSD-3-Clause
- python-multipart 0.0.32: Apache-2.0
- Typer 0.27.0: MIT
- Uvicorn 0.52.1: BSD-3-Clause

Their transitive dependencies retain their upstream copyright and license
terms. Exact resolved versions are recorded in `uv.lock`.

## Build tooling

- PyInstaller 6.21.0: GPL version 2 or later with the PyInstaller exception
  permitting distribution of programs built with PyInstaller.

Upstream project and source URLs are recorded in `tools/manifest.json`,
`java-worker/pom.xml`, `pyproject.toml` and `uv.lock`.
