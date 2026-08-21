!ifndef APP_SOURCE
  !error "APP_SOURCE is required"
!endif
!ifndef OUTPUT_FILE
  !error "OUTPUT_FILE is required"
!endif
!ifndef ICON_FILE
  !error "ICON_FILE is required"
!endif
!ifndef PRODUCT_VERSION
  !error "PRODUCT_VERSION is required"
!endif
!ifndef PRODUCT_DISPLAY_VERSION
  !error "PRODUCT_DISPLAY_VERSION is required"
!endif

!include "MUI2.nsh"
!include "x64.nsh"

Unicode true
Name "围标串标投标人名称一致检测工具"
OutFile "${OUTPUT_FILE}"
InstallDir "$LOCALAPPDATA\Programs\DocumentMetadataInspector"
InstallDirRegKey HKCU "Software\DocumentMetadataInspector" "InstallLocation"
RequestExecutionLevel user
ManifestSupportedOS Win10
SetCompressor /SOLID lzma
Icon "${ICON_FILE}"
UninstallIcon "${ICON_FILE}"

VIProductVersion "${PRODUCT_VERSION}"
VIAddVersionKey /LANG=2052 "ProductName" "围标串标投标人名称一致检测工具"
VIAddVersionKey /LANG=2052 "FileDescription" "围标串标投标人名称一致检测工具安装程序"
VIAddVersionKey /LANG=2052 "FileVersion" "${PRODUCT_DISPLAY_VERSION}"
VIAddVersionKey /LANG=2052 "ProductVersion" "${PRODUCT_DISPLAY_VERSION}"
VIAddVersionKey /LANG=2052 "LegalCopyright" "Document Metadata Inspector Contributors"

!define MUI_ABORTWARNING
!define MUI_ICON "${ICON_FILE}"
!define MUI_UNICON "${ICON_FILE}"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "本程序仅支持 Windows 10/11 x64。"
    Abort
  ${EndIf}
FunctionEnd

Section "围标串标投标人名称一致检测工具" MainSection
  SectionIn RO
  SetRegView 64
  SetOutPath "$INSTDIR"
  File /r "${APP_SOURCE}/*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateDirectory "$SMPROGRAMS\围标串标投标人名称一致检测工具"
  CreateShortcut "$SMPROGRAMS\围标串标投标人名称一致检测工具\围标串标投标人名称一致检测工具.lnk" \
    "$INSTDIR\docmeta-review.exe"
  CreateShortcut "$SMPROGRAMS\围标串标投标人名称一致检测工具\卸载围标串标投标人名称一致检测工具.lnk" \
    "$INSTDIR\Uninstall.exe"

  WriteRegStr HKCU "Software\DocumentMetadataInspector" \
    "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU \
    "Software\Microsoft\Windows\CurrentVersion\Uninstall\DocumentMetadataInspector" \
    "DisplayName" "围标串标投标人名称一致检测工具"
  WriteRegStr HKCU \
    "Software\Microsoft\Windows\CurrentVersion\Uninstall\DocumentMetadataInspector" \
    "DisplayVersion" "${PRODUCT_DISPLAY_VERSION}"
  WriteRegStr HKCU \
    "Software\Microsoft\Windows\CurrentVersion\Uninstall\DocumentMetadataInspector" \
    "Publisher" "Document Metadata Inspector Contributors"
  WriteRegStr HKCU \
    "Software\Microsoft\Windows\CurrentVersion\Uninstall\DocumentMetadataInspector" \
    "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU \
    "Software\Microsoft\Windows\CurrentVersion\Uninstall\DocumentMetadataInspector" \
    "DisplayIcon" "$INSTDIR\docmeta-review.exe"
  WriteRegStr HKCU \
    "Software\Microsoft\Windows\CurrentVersion\Uninstall\DocumentMetadataInspector" \
    "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKCU \
    "Software\Microsoft\Windows\CurrentVersion\Uninstall\DocumentMetadataInspector" \
    "NoModify" 1
  WriteRegDWORD HKCU \
    "Software\Microsoft\Windows\CurrentVersion\Uninstall\DocumentMetadataInspector" \
    "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetRegView 64
  Delete "$SMPROGRAMS\围标串标投标人名称一致检测工具\围标串标投标人名称一致检测工具.lnk"
  Delete "$SMPROGRAMS\围标串标投标人名称一致检测工具\卸载围标串标投标人名称一致检测工具.lnk"
  RMDir "$SMPROGRAMS\围标串标投标人名称一致检测工具"
  DeleteRegKey HKCU \
    "Software\Microsoft\Windows\CurrentVersion\Uninstall\DocumentMetadataInspector"
  DeleteRegKey HKCU "Software\DocumentMetadataInspector"
  RMDir /r "$INSTDIR"
SectionEnd
