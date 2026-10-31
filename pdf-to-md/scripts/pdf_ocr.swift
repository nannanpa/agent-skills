// pdf_ocr.swift — PDF → 渲染 → 离线中文 OCR → 带页标记的中间产物（pdf-to-md 1.2.1 配套）
//
// 为什么需要它：纯扫描件 PDF 没有文字层，pdf_extract.py 只能提取出空文本。
// 原来的链路要人工做两件事：①把 PDF 渲染成 PNG（曾依赖 PyMuPDF，macOS 上往往没装）
// ②OCR 之后手工补 `<!-- 第 N 页 -->` 页标记。两处都是断点，漏一处后面就全乱。
//
// 本脚本把三步接成一步，且**只用 macOS 自带框架**（PDFKit 渲染 + Vision 识别），
// 零安装、零网络、零 Python 依赖。
//
// 用法：
//   swift pdf_ocr.swift 输入.pdf 输出.md [选项]
//     --dpi N              渲染分辨率（默认 150；公文小字可加到 200）
//     --page N             只处理第 N 页（1 起），核字用
//     --coords             输出置信度与坐标（confidence x y 宽 高）
//     --render-only        只把 PDF 渲染成 PNG（放在 --png-dir 指定目录），不做 OCR
//     --png-dir DIR        PNG 输出目录（默认与输出.md 同目录下的 <名字>_pages/）
//     --low-conf X         置信度低于 X 的行在行尾加〔OCR待核〕标记（默认 0.5；0 表示不标）
//     --langs a,b          识别语言（默认 zh-Hans,en-US）
//     --no-hdr             不识别页眉/页脚（默认识别）
//
// 输出格式与 pdf_extract.py **完全一致**（`# <文件名> 提取文本` + `<!-- 第 N 页 -->`），
// 因此产物可以直接喂给 clean_md.py。
//
// 重要：本工具只做"机器读字"，不保证读对。输出必须**逐处回图校验**——
// 2026-10-30 实测在一份 2011 年传真件上，Vision 把"2012年7月"读成"2012年1月"、
// "教学要求"读成"数学要求"，另有十余处形近误识（儒求/带求→需求、脈属→隶属、
// 授子→授予、硬士→硕士、姿员会→委员会、备菜→备案…）。凡涉及日期、数字、
// 机构名、人名的，一律回图确认。低置信度行会带〔OCR待核〕，是回图的优先清单。

import Foundation
import PDFKit
import Vision
import AppKit

// ── 参数解析 ─────────────────────────────────────────────────────────────
var positional: [String] = []
var dpi: Double = 150
var onlyPage: Int? = nil
var wantCoords = false
var renderOnly = false
var pngDir: String? = nil
var lowConf: Double = 0.5
var langs = ["zh-Hans", "en-US"]
var detectHeader = true

var argv = Array(CommandLine.arguments.dropFirst())
var i = 0

/// 取当前选项的值；选项处在末尾缺值时报错退 2（防 argv[i] 越界崩溃）。
/// 各取值型 case 统一走它——谁都不许直接下标 argv[i]。
func takeValue(_ option: String, _ usage: String) -> String {
    i += 1
    guard i < argv.count else {
        FileHandle.standardError.write("选项 \(option) 缺少取值。\n用法: swift pdf_ocr.swift 输入.pdf 输出.md \(usage)\n".data(using: .utf8)!)
        exit(2)
    }
    return argv[i]
}

while i < argv.count {
    let a = argv[i]
    switch a {
    case "--dpi":
        dpi = Double(takeValue(a, "--dpi N")) ?? 150
    case "--page":
        onlyPage = Int(takeValue(a, "--page N（1 起）"))
    case "--coords":
        wantCoords = true
    case "--render-only":
        renderOnly = true
    case "--png-dir":
        pngDir = takeValue(a, "--png-dir DIR")
    case "--low-conf":
        lowConf = Double(takeValue(a, "--low-conf X")) ?? 0.5
    case "--langs":
        langs = takeValue(a, "--langs a,b").split(separator: ",").map(String.init)
    case "--no-hdr":
        detectHeader = false
    case "-h", "--help":
        print("用法: swift pdf_ocr.swift 输入.pdf 输出.md [--dpi N] [--page N] [--coords] [--render-only] [--png-dir DIR] [--low-conf X] [--langs a,b] [--no-hdr]")
        exit(0)
    default:
        positional.append(a)
    }
    i += 1
}

guard positional.count >= 2 else {
    FileHandle.standardError.write("用法: swift pdf_ocr.swift 输入.pdf 输出.md [选项]\n".data(using: .utf8)!)
    exit(1)
}
let srcPath = positional[0]
let dstPath = positional[1]

let fm = FileManager.default
guard fm.fileExists(atPath: srcPath) else {
    FileHandle.standardError.write("找不到文件: \(srcPath)\n".data(using: .utf8)!)
    exit(1)
}
guard let doc = PDFDocument(url: URL(fileURLWithPath: srcPath)) else {
    FileHandle.standardError.write("打不开 PDF（可能加密或损坏）: \(srcPath)\n".data(using: .utf8)!)
    exit(1)
}

// ── PNG 输出目录 ─────────────────────────────────────────────────────────
let defaultDir = (dstPath as NSString).deletingLastPathComponent
let baseName = ((dstPath as NSString).lastPathComponent as NSString).deletingPathExtension
let outDir = pngDir ?? (defaultDir.isEmpty ? "\(baseName)_pages" : "\(defaultDir)/\(baseName)_pages")
try? fm.createDirectory(atPath: outDir, withIntermediateDirectories: true)

// ── 渲染：PDFKit → PNG ──────────────────────────────────────────────────
/// 渲染一页为 PNG 文件，返回文件路径。
func renderPage(_ page: PDFPage, to path: String) -> Bool {
    let b = page.bounds(for: .mediaBox)
    let scale = dpi / 72.0
    let size = NSSize(width: b.width * scale, height: b.height * scale)
    let img = NSImage(size: size)
    img.lockFocus()
    NSColor.white.setFill()
    NSRect(origin: .zero, size: size).fill()
    if let ctx = NSGraphicsContext.current?.cgContext {
        ctx.saveGState()
        ctx.scaleBy(x: scale, y: scale)
        page.draw(with: .mediaBox, to: ctx)
        ctx.restoreGState()
    }
    img.unlockFocus()
    guard let tiff = img.tiffRepresentation,
          let rep = NSBitmapImageRep(data: tiff),
          let png = rep.representation(using: .png, properties: [:]) else { return false }
    try? png.write(to: URL(fileURLWithPath: path))
    return true
}

// ── OCR：Vision ──────────────────────────────────────────────────────────
/// 识别单张图片 → [(置信度, 文本, 归一化x, 归一化y, 宽, 高)]
func recognize(_ imgPath: String) -> [(Double, String, Double, Double, Double, Double)] {
    guard let img = NSImage(contentsOfFile: imgPath),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return [] }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate          // 准确优先，慢于 fast 但公文够用
    req.recognitionLanguages = langs
    req.usesLanguageCorrection = true
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    do { try handler.perform([req]) } catch { return [] }
    guard let obs = req.results else { return [] }
    var out: [(Double, String, Double, Double, Double, Double)] = []
    for o in obs {
        guard let c = o.topCandidates(1).first else { continue }
        let bb = o.boundingBox
        out.append((Double(c.confidence), c.string,
                    Double(bb.minX), Double(bb.minY),
                    Double(bb.width), Double(bb.height)))
    }
    return out
}

/// 逐行排序：y 降序（Vision 原点在左下，故 y 大的在上），同行按 x 升序
func byLine(_ a: (Double, String, Double, Double, Double, Double),
            _ b: (Double, String, Double, Double, Double, Double)) -> Bool {
    if abs(a.3 - b.3) > 0.008 { return a.3 > b.3 }
    return a.2 < b.2
}

// ── 主流程：先全部渲染 + OCR（页眉页脚判定需要跨页信息），再统一输出 ─────
typealias Line = (Double, String, Double, Double, Double, Double)
let srcName = (srcPath as NSString).lastPathComponent
var pageResults: [(Int, [Line])] = []
var rendered = 0

for idx in 0..<doc.pageCount {
    let pageNo = idx + 1
    if let p = onlyPage, p != pageNo { continue }
    guard let page = doc.page(at: idx) else { continue }

    let pngPath = "\(outDir)/page_\(pageNo).png"
    if renderOnly {
        if renderPage(page, to: pngPath) {
            rendered += 1
            print("渲染 \(pngPath)")
        } else {
            print("⚠ 第 \(pageNo) 页渲染失败")
        }
        continue
    }

    guard renderPage(page, to: pngPath) else {
        print("⚠ 第 \(pageNo) 页渲染失败，跳过")
        continue
    }
    rendered += 1

    let res = recognize(pngPath).sorted(by: byLine)
    pageResults.append((pageNo, res))
    print("第 \(pageNo) 页：\(res.count) 行")
}

// ── 页眉/页脚识别 ────────────────────────────────────────────────────────
// 痛点：传真件/连续装订的扫描件，每页页顶页脚都有发件方信息、时间戳、号码，
// OCR 后全部混进正文。纯文本跨页匹配不可靠（同一页眉每次 OCR 结果可能有细微
// 差异，实测 "628811662227" 与 "628811662221" 同页眉两种结果）。
// 改用**几何判据**：行中心落在页顶/页底 7% 之内，且**不止一页**在该区域有行。
// 这样既能命中每页重复的传真页眉，又不会误伤第 1 页顶部的发文机关标志
//（实测"国务院学位委员会文件"在 y≈0.75，远离页顶 7%）。
// 与本技能一贯口径一致：**只打标，不删行**——删不删由人决定。
var edgePages = 0
var isHeader: Set<String> = []
if detectHeader && pageResults.count >= 2 {
    // 元组字段：r.0=conf r.1=text r.2=x r.3=y r.4=宽 r.5=高
    // 行中心 y = y + 高/2（**不是宽**——写错会把宽行误判成页眉）
    for (_, res) in pageResults {
        if res.contains(where: { $0.3 + $0.5 / 2 > 0.93 || $0.3 + $0.5 / 2 < 0.07 }) {
            edgePages += 1
        }
    }
    if edgePages >= 2 {
        for (pno, res) in pageResults {
            for r in res {
                let yc = r.3 + r.5 / 2
                if yc > 0.93 || yc < 0.07 {
                    isHeader.insert("\(pno)|\(r.1)")
                }
            }
        }
    }
}

var parts: [String] = ["# \(srcName) 提取文本\n"]
var totalLow = 0
var totalLines = 0
var totalHdr = 0

for (pageNo, res) in pageResults {
    if res.isEmpty {
        parts.append("\n\n---\n\n<!-- 第 \(pageNo) 页 -->\n\n")
        continue
    }
    var lines: [String] = []
    for (conf, text, x, y, w, h) in res {
        if wantCoords {
            lines.append(String(format: "%.2f\t%.4f\t%.4f\t%.4f\t%.4f\t%@",
                                conf, x, y, w, h, text))
        } else {
            var t = text
            if lowConf > 0 && conf < lowConf {
                t += "〔OCR待核〕"
                totalLow += 1
            }
            if isHeader.contains("\(pageNo)|\(text)") {
                t += "〔页眉页脚〕"
                totalHdr += 1
            }
            lines.append(t)
        }
        totalLines += 1
    }
    parts.append("\n\n---\n\n<!-- 第 \(pageNo) 页 -->\n\n\(lines.joined(separator: "\n"))")
}

if renderOnly {
    print("完成：渲染 \(rendered) 页 → \(outDir)")
    exit(0)
}

do {
    try (parts.joined(separator: "\n") + "\n").write(toFile: dstPath, atomically: true, encoding: .utf8)
} catch {
    FileHandle.standardError.write("写入失败 \(dstPath): \(error)\n".data(using: .utf8)!)
    exit(1)
}
print("完成: \(dstPath)  共\(doc.pageCount)页 / \(rendered)页已渲染 / \(totalLines)行")
if totalLow > 0 {
    print("⚠ \(totalLow) 行置信度低于 \(lowConf)，已标〔OCR待核〕——请回图逐处核对（用 --page N --coords 定位）")
}
if totalHdr > 0 {
    print("ℹ \(totalHdr) 行落在页顶/页底 7% 且多页同区出现（几何判据，不比文本），判为页眉/页脚，已标〔页眉页脚〕（未删行）")
}
