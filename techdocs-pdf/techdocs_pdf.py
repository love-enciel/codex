from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import time
import traceback

from playwright.sync_api import (
    sync_playwright,
    Error as PlaywrightError,
)
from pypdf import PdfWriter


START_URL = (
    "https://techdocs.akamai.com"
    "/segmentation-v52/docs/welcome-guardicore"
)
DOC_PREFIX = "https://techdocs.akamai.com/segmentation-v52/docs/"
LINK_SELECTOR = "a[href]"

BASE_DIR = Path(__file__).resolve().parent
PROFILE_DIR = BASE_DIR / "techdocs_browser_profile"


def clean_url(url):
    parts = urlsplit(url)
    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        "",  # 추적용 쿼리 제거
        "",  # 페이지 내부 위치 제거
    ))


def is_doc_url(url):
    return clean_url(url).startswith(DOC_PREFIX)


def select_document_page(browser):
    pages = [page for page in browser.pages if not page.is_closed()]
    if not pages:
        raise RuntimeError("스크립트가 연 Chromium에 열린 탭이 없습니다.")

    print("\n스크립트가 제어하는 브라우저 탭:")
    for index, page in enumerate(pages, 1):
        # 로그인 토큰 등이 포함될 수 있는 쿼리는 표시하지 않습니다.
        print(f"{index}. {clean_url(page.url)}")

    answer = input(
        "\n문서가 열린 탭 번호를 입력하세요 (Enter: 마지막 탭): "
    ).strip()
    if not answer:
        return pages[-1]
    try:
        index = int(answer) - 1
        if 0 <= index < len(pages):
            return pages[index]
    except ValueError:
        pass
    raise RuntimeError("탭 번호가 올바르지 않습니다. 다시 실행하세요.")


def collect_links(browser):
    for attempt in range(1, 11):
        page = select_document_page(browser)

        if page is None:
            input(
                "\n브라우저에서 Segmentation v5.2 문서를 여세요.\n"
                "로그인과 로딩이 끝나면 여기서 Enter를 누르세요..."
            )
            continue

        try:
            page.wait_for_load_state(
                "domcontentloaded",
                timeout=30000,
            )

            page.locator(LINK_SELECTOR).first.wait_for(
                state="attached",
                timeout=30000,
            )

            # URL과 링크를 같은 실행 컨텍스트에서 수집합니다.
            snapshot = page.evaluate(
                r"""
                selector => ({
                    url: location.href,
                    title: document.title,
                    links: Array.from(
                        document.querySelectorAll(selector)
                    ).map(element => ({
                        title: (
                            element.innerText ||
                            element.textContent ||
                            ""
                        ).trim().replace(/\s+/g, " "),
                        url: element.href
                    }))
                })
                """,
                LINK_SELECTOR,
            )

            if not is_doc_url(snapshot["url"]):
                raise RuntimeError(
                    "선택한 탭의 주소가 수집 대상과 다릅니다.\n"
                    f"실제 주소: {clean_url(snapshot['url'])}\n"
                    f"설정된 주소 범위: {DOC_PREFIX}\n"
                    "위 주소를 확인해 주세요."
                )

            candidates = []
            seen = set()

            items = [{
                "title": snapshot["title"] or "현재 페이지",
                "url": snapshot["url"],
            }] + snapshot["links"]

            for item in items:
                url = clean_url(item["url"])

                if not is_doc_url(url) or url in seen:
                    continue

                seen.add(url)
                candidates.append({
                    "title": item["title"] or url.rsplit("/", 1)[-1],
                    "url": url,
                })

            return page, candidates

        except PlaywrightError as error:
            print(
                f"\n링크 수집 재시도 {attempt}/10\n"
                f"{error}"
            )
            time.sleep(2)

    raise RuntimeError(
        "문서 링크를 수집하지 못했습니다. "
        "로그인 상태와 문서 탭을 확인하세요."
    )


def prepare_document(page, url):
    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=60000,
    )

    if clean_url(page.url) != clean_url(url):
        raise RuntimeError(
            f"다른 페이지로 이동했습니다: {page.url}\n"
            "로그인이 필요한지 확인하세요."
        )

    # 본문이 실제로 표시될 때까지 기다립니다.
    page.locator(
        "article, .rm-Markdown, .markdown-body"
    ).first.wait_for(
        state="visible",
        timeout=30000,
    )

    page.evaluate(
        """
        async () => {
            for (const image of document.images) {
                image.loading = "eager";
            }

            await Promise.race([
                document.fonts.ready,
                new Promise(resolve => setTimeout(resolve, 10000))
            ]);

            await Promise.all(
                Array.from(document.images).map(image => {
                    if (image.complete) return Promise.resolve();

                    return new Promise(resolve => {
                        image.addEventListener(
                            "load", resolve, {once: true}
                        );
                        image.addEventListener(
                            "error", resolve, {once: true}
                        );
                        setTimeout(resolve, 10000);
                    });
                })
            );
        }
        """
    )

    page.wait_for_timeout(1500)


def export_pdf(page, item, destination):
    for attempt in range(1, 4):
        try:
            prepare_document(page, item["url"])

            page.pdf(
                path=str(destination),
                format="A4",
                print_background=True,
                margin={
                    "top": "12mm",
                    "right": "10mm",
                    "bottom": "12mm",
                    "left": "10mm",
                },
            )
            return

        except (PlaywrightError, RuntimeError) as error:
            if attempt == 3 or page.is_closed():
                raise

            print(f"  PDF 저장 재시도 {attempt}/3: {error}")
            time.sleep(2)


def run(browser, output_dir):
    page = browser.pages[0] if browser.pages else browser.new_page()

    try:
        page.goto(
            START_URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )
    except PlaywrightError as error:
        print(f"\n첫 페이지 열기 오류: {error}")
        print("열린 브라우저에서 직접 문서 URL로 이동해도 됩니다.")

    print("\n브라우저에서 필요하면 로그인하세요.")
    print("왼쪽 문서 메뉴에서 저장하려는 항목을 모두 펼치세요.")
    print("로그인과 페이지 로딩이 완전히 끝날 때까지 기다리세요.")
    input("\n준비가 끝나면 여기서 Enter를 누르세요...")

    while True:
        page, candidates = collect_links(browser)

        print(f"\n수집한 문서: {len(candidates)}개\n")
        for index, item in enumerate(candidates, 1):
            print(f'{index:4}. {item["title"]}')
            print(f'      {item["url"]}')

        print("\n현재 화면에 링크가 있는 문서만 수집합니다.")
        print("접힌 메뉴의 문서는 누락될 수 있습니다.")
        answer = input(
            "\n저장: y / 메뉴를 펼친 뒤 다시 수집: r / 종료: n\n"
            "선택: "
        ).strip().lower()

        if answer == "r":
            input(
                "\n브라우저에서 메뉴를 펼친 뒤 "
                "여기서 Enter를 누르세요..."
            )
            continue

        if answer != "y":
            print("취소했습니다.")
            return

        break

    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "sources.txt").write_text(
        "\n".join(
            f'{item["title"]}\t{item["url"]}'
            for item in candidates
        ),
        encoding="utf-8",
    )

    successful = []
    failures = []

    # 수집한 탭과 별도의 탭에서 PDF를 생성합니다.
    pdf_page = browser.new_page()

    try:
        for index, item in enumerate(candidates, 1):
            destination = output_dir / f"{index:04d}.pdf"
            print(
                f'\n[{index}/{len(candidates)}] '
                f'{item["title"]}'
            )

            if pdf_page.is_closed():
                pdf_page = browser.new_page()

            try:
                export_pdf(pdf_page, item, destination)
                successful.append((destination, item["title"]))
                print("  저장 완료")

            except Exception as error:
                print(f"  저장 실패: {error}")
                failures.append(
                    f'{item["url"]}\n{error}\n'
                )

    finally:
        if not pdf_page.is_closed():
            pdf_page.close()

        # 중간에 작업이 중단되어도 완료된 PDF는 병합합니다.
        if successful:
            merged_path = output_dir / "techdocs_merged.pdf"
            writer = PdfWriter()

            try:
                for pdf_path, title in successful:
                    writer.append(
                        str(pdf_path),
                        outline_item=title,
                    )

                with merged_path.open("wb") as output:
                    writer.write(output)

            finally:
                writer.close()

            print(f"\n병합 PDF: {merged_path}")
            print(f"저장 성공: {len(successful)}개")

        if failures:
            failure_path = output_dir / "failures.txt"
            failure_path.write_text(
                "\n".join(failures),
                encoding="utf-8",
            )
            print(f"저장 실패: {len(failures)}개")
            print(f"실패 목록: {failure_path}")

        print(f"\n저장 폴더: {output_dir}")


def main():
    output_dir = (
        BASE_DIR
        / "techdocs_pdf"
        / datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    with sync_playwright() as playwright:
        browser = None

        try:
            browser = playwright.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                headless=False,
                accept_downloads=True,
            )

            run(browser, output_dir)

        except KeyboardInterrupt:
            print("\n작업이 중단되었습니다.")

        except Exception:
            error_text = traceback.format_exc()
            print(f"\n오류가 발생했습니다.\n{error_text}")

            try:
                output_dir.mkdir(parents=True, exist_ok=True)
                error_path = output_dir / "error_log.txt"
                error_path.write_text(
                    error_text,
                    encoding="utf-8",
                )
                print(f"오류 기록: {error_path}")
            except OSError:
                pass

        finally:
            # 예외가 발생해도 확인 전까지 브라우저를 유지합니다.
            if browser is not None:
                try:
                    input(
                        "\n확인이 끝나면 Enter를 누르세요. "
                        "브라우저를 종료합니다..."
                    )
                except (EOFError, KeyboardInterrupt):
                    pass

                try:
                    browser.close()
                except PlaywrightError:
                    pass


if __name__ == "__main__":
    main()