// ocr_vision.swift — macOS 自带 Vision 框架的离线中文 OCR（pdf-to-md 1.2.0 配套）
//
// 为什么需要它：纯扫描件 PDF 没有文字层，第 1 步 pdf_extract.py 只能提取出空文本。
// 常见做法是装 PaddleOCR / Tesseract——都要额外依赖，且默认装不上。
// macOS 自带 Vision，/usr/bin/swift 可直接跑，零安装、零网络、中文简体可识别。
//
// 用法：
//   swift ocr_vision.swift <图片目录>            批量：逐张识别，按行序输出到同名 .txt
//   swift ocr_vision.swift <单张图片> --coords    单张：带置信度与坐标输出（confidence/x/y）
//
// 依赖：macOS 10.15+（Vision）、Xcode 命令行工具（/usr/bin/swift）。
// 注意：Vision 的 boundingBox 原点在**左下角**，转图像素坐标时须翻转 y。
//
// 重要：本工具只做"机器读字"，不保证读对。输出必须**逐处回图校验**——
// 2026-10-30 实测在一份 2011 年传真件上，Vision 把"2012年7月"读成"2012年1月"、
// "教学要求"读成"数学要求"，另有十余处形近误识。机器读字是起点，不是结论。

import Foundation
import Vision
import AppKit

let args = CommandLine.arguments
guard args.count >= 2 else {
    FileHandle.standardError.write("用法: swift ocr_vision.swift <图片目录|单张图片> [--coords]\n".data(using: .utf8)!)
    exit(1)
}
let wantCoords = args.contains("--coords")
let path = args[1]
let fm = FileManager.default
var isDir: ObjCBool = false
guard fm.fileExists(atPath: path, isDirectory: &isDir) else {
    FileHandle.standardError.write("路径不存在: \(path)\n".data(using: .utf8)!)
    exit(1)
}

/// 识别单张图片 → [(置信度, 文本, 归一化x, 归一化y, 宽, 高)]
func recognize(_ imgPath: String) -> [(Double, String, Double, Double, Double, Double)] {
    guard let img = NSImage(contentsOfFile: imgPath),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return [] }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate          // 准确优先，慢于 fast 但公文够用
    req.recognitionLanguages = ["zh-Hans", "en-US"]
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

if isDir.boolValue {
    // 批量模式：按文件名排序逐张处理，输出到同名 .txt
    let names = (try? fm.contentsOfDirectory(atPath: path))?
        .filter { $0.hasSuffix(".png") || $0.hasSuffix(".jpg") || $0.hasSuffix(".jpeg") }
        .sorted() ?? []
    for name in names {
        let full = (path as NSString).appendingPathComponent(name)
        let res = recognize(full)
        // 按行序：y 降序（Vision 原点在左下，故 y 大的在上），同行按 x 升序
        let sorted = res.sorted { a, b in
            if abs(a.3 - b.3) > 0.008 { return a.3 > b.3 }
            return a.2 < b.2
        }
        let lines = sorted.map { $0.1 }
        let out = (path as NSString).appendingPathComponent(
            (name as NSString).deletingPathExtension + ".txt")
        try lines.joined(separator: "\n").write(toFile: out, atomically: true, encoding: .utf8)
        print("\(name) -> \(lines.count) 行")
    }
} else {
    // 单张模式：带坐标输出，用于按行定位并回图核字
    let res = recognize(path)
    if res.isEmpty {
        FileHandle.standardError.write("未识别到文本：\(path)\n".data(using: .utf8)!)
        exit(2)
    }
    for (conf, text, x, y, w, h) in res {
        print(String(format: "%.2f\t%.4f\t%.4f\t%.4f\t%.4f\t%@",
                     conf, x, y, w, h, text))
    }
}
