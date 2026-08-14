#!/usr/bin/osascript
-- 한컴오피스 한글(macOS) UI 자동화로 HWP/HWPX → PDF 변환.
-- 요금 없음. 접근성(Accessibility) 권한이 필요합니다.
-- 사용: osascript hancom_hwp_to_pdf.applescript "/abs/in.hwp" "/abs/out.pdf"

on run argv
	if (count of argv) < 2 then
		error "사용법: osascript hancom_hwp_to_pdf.applescript <input.hwp> <output.pdf>"
	end if
	set inputPath to item 1 of argv
	set outputPath to item 2 of argv
	return my convertHwpToPdf(inputPath, outputPath)
end run

on convertHwpToPdf(inputPath, outputPath)
	set inputPOSIX to inputPath as string
	set outputPOSIX to outputPath as string
	set inputAlias to POSIX file inputPOSIX
	set outputFolderPOSIX to do shell script "dirname " & quoted form of outputPOSIX
	set outputName to do shell script "basename " & quoted form of outputPOSIX

	-- 한컴이 파일 연결로 열리도록 합니다.
	try
		do shell script "open -a " & quoted form of "Hancom Office HWP" & " " & quoted form of inputPOSIX
	on error errMsg number errNum
		error "한컴오피스 한글을 열 수 없습니다 (" & errNum & "): " & errMsg
	end try

	delay 1.2
	tell application "Hancom Office HWP" to activate
	delay 0.8

	try
		tell application "System Events"
			if not (exists process "Hancom Office HWP") then
				error "Hancom Office HWP 프로세스가 없습니다. 접근성 권한 또는 앱 실행을 확인하세요."
			end if

			tell process "Hancom Office HWP"
				set frontmost to true
				delay 0.4

				-- 호환성/복구 확인 창이 있으면 기본 확인을 누릅니다.
				my dismissAlerts()

				-- ⌘P → 인쇄 시트
				keystroke "p" using {command down}
				delay 1.0

				-- 인쇄 시트의 PDF 메뉴 → PDF로 저장
				set saved to false
				repeat with attempt from 1 to 8
					try
						if exists sheet 1 of window 1 then
							tell sheet 1 of window 1
								-- 버튼 이름이 로케일에 따라 다릅니다.
								set pdfButton to missing value
								repeat with b in buttons
									set bn to name of b as string
									if bn contains "PDF" then
										set pdfButton to b
										exit repeat
									end if
								end repeat
								if pdfButton is missing value then
									-- 일부 버전은 메뉴 버튼/팝업으로만 노출됩니다.
									try
										click menu button 1
									end try
								else
									click pdfButton
								end if
							end tell
							delay 0.35
							-- PDF 메뉴 항목 선택
							try
								click menu item "PDF로 저장…" of menu 1 of sheet 1 of window 1
								set saved to true
							on error
								try
									click menu item "Save as PDF…" of menu 1 of sheet 1 of window 1
									set saved to true
								on error
									-- 메뉴가 프로세스 최상단에 붙는 경우
									try
										click menu item "PDF로 저장…" of menu 1
										set saved to true
									on error
										click menu item "Save as PDF…" of menu 1
										set saved to true
									end try
								end try
							end try
							if saved then exit repeat
						end if
					end try
					delay 0.4
				end repeat

				if not saved then
					keystroke "w" using {command down}
					error "인쇄 시트에서 'PDF로 저장'을 찾지 못했습니다."
				end if

				delay 0.8
				-- 저장 패널: 폴더 이동(⌘⇧G) 후 파일명 입력
				keystroke "g" using {command down, shift down}
				delay 0.5
				keystroke outputFolderPOSIX
				delay 0.2
				keystroke return
				delay 0.6

				-- 파일명 필드 선택 후 덮어쓰기
				keystroke "a" using {command down}
				delay 0.1
				keystroke outputName
				delay 0.2
				keystroke return
				delay 0.8

				-- 덮어쓰기 확인
				try
					if exists sheet 1 of window 1 then
						tell sheet 1 of window 1
							repeat with b in buttons
								set bn to name of b as string
								if bn is "Replace" or bn is "대체" or bn is "덮어쓰기" or bn contains "Replace" then
									click b
									exit repeat
								end if
							end repeat
						end tell
					end if
				end try

				-- 인쇄/저장이 끝날 때까지 대기
				repeat with i from 1 to 40
					delay 0.5
					set stillPrinting to false
					try
						if exists sheet 1 of window 1 then set stillPrinting to true
					end try
					if not stillPrinting then exit repeat
				end repeat

				-- 문서 창 닫기(저장 안 함)
				keystroke "w" using {command down}
				delay 0.4
				try
					if exists sheet 1 of window 1 then
						tell sheet 1 of window 1
							repeat with b in buttons
								set bn to name of b as string
								if bn is "Don't Save" or bn is "저장 안 함" or bn contains "Don" then
									click b
									exit repeat
								end if
							end repeat
						end tell
					end if
				end try
			end tell
		end tell
	on error errMsg number errNum
		-- 접근성 거부(-1719) 등을 호출자에게 전달
		error errMsg number errNum
	end try

	-- 결과 파일 확인
	set checkCmd to "test -s " & quoted form of outputPOSIX & " && echo OK || echo FAIL"
	set checkResult to do shell script checkCmd
	if checkResult is not "OK" then
		error "PDF 파일이 생성되지 않았습니다: " & outputPOSIX
	end if
	return outputPOSIX
end convertHwpToPdf

on dismissAlerts()
	tell application "System Events"
		tell process "Hancom Office HWP"
			try
				if exists sheet 1 of window 1 then
					tell sheet 1 of window 1
						repeat with b in buttons
							set bn to name of b as string
							if bn is "OK" or bn is "확인" or bn is "열기" or bn is "Open" or bn is "예" or bn is "Yes" then
								click b
								exit repeat
							end if
						end repeat
					end tell
				end if
			end try
		end tell
	end tell
end dismissAlerts
