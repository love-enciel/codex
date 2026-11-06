# Akamai TechDocs PDF 저장

Segmentation v5.2 문서를 Chromium에서 열고, 현재 페이지에 연결된 문서를 개별 PDF 및 책갈피가 포함된 병합 PDF로 저장합니다.

## Windows 실행

Python이 설치된 PC에서 이 폴더를 다운로드하고 터미널을 엽니다.

```powershell
py -m pip install -r requirements.txt
py -m playwright install chromium
py techdocs_pdf.py
```

1. 스크립트가 연 Chromium에서 필요하면 로그인합니다. 평소 사용하는 별도의 Chrome 창은 제어 대상이 아닙니다.
2. 왼쪽 문서 메뉴를 모두 펼치고 로딩이 끝나면 터미널에서 Enter를 누릅니다.
3. 출력된 목록에서 문서 탭 번호를 선택합니다.
4. 수집 목록을 확인하고 `y`를 입력합니다. 메뉴를 더 펼친 뒤 다시 수집하려면 `r`을 입력합니다.
5. `techdocs_pdf/실행날짜_시간/techdocs_merged.pdf`를 확인합니다.

개별 PDF, `sources.txt`, 실패 시 `failures.txt` 또는 `error_log.txt`도 같은 출력 폴더에 저장됩니다. 오류가 발생해도 종료 확인 전까지 브라우저를 유지합니다.

## 범위와 검증

- 대상 URL 범위: `https://techdocs.akamai.com/segmentation-v52/docs/`
- 선택한 탭에 링크가 있는 문서만 수집하므로 접힌 메뉴나 링크가 없는 문서는 누락될 수 있습니다. 사이트 전체 재귀 수집은 하지 않습니다.
- Python 구문 검사를 통과했습니다. 작업 환경의 사이트 연결 문제로 실제 사이트에서 PDF 생성은 검증하지 못했습니다.
- 로그인 세션은 로컬 `techdocs_browser_profile/`에 저장됩니다. 이 폴더와 생성된 PDF는 Git에 포함하지 않습니다.

macOS/Linux에서는 `py` 대신 `python3`를 사용하세요.
