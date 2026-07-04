import Foundation
import Vision
import AppKit

// Check arguments
guard CommandLine.arguments.count > 1 else {
    print("Error: Missing file path argument")
    exit(1)
}

let filePath = CommandLine.arguments[1]
let url = URL(fileURLWithPath: filePath)

// Load image using CIImage or NSImage (CIImage is faster and doesn't require AppKit NSImage tiff conversion)
guard let ciImage = CIImage(contentsOf: url) else {
    print("{\"error\": \"Could not load image\"}")
    exit(1)
}

let requestHandler = VNImageRequestHandler(ciImage: ciImage, options: [:])

var tags: [String] = []
var ocrText: [String] = []

// 1. Image Classification Request
let classificationRequest = VNClassifyImageRequest { request, error in
    guard let results = request.results as? [VNClassificationObservation] else { return }
    for classification in results.prefix(8) {
        if classification.confidence > 0.1 {
            tags.append(classification.identifier)
        }
    }
}

// 2. OCR Text Recognition Request
let ocrRequest = VNRecognizeTextRequest { request, error in
    guard let results = request.results as? [VNRecognizedTextObservation] else { return }
    for observation in results {
        if let topCandidate = observation.topCandidates(1).first {
            ocrText.append(topCandidate.string)
        }
    }
}
ocrRequest.recognitionLevel = .fast

do {
    try requestHandler.perform([classificationRequest, ocrRequest])
    
    let dict: [String: Any] = [
        "tags": tags,
        "text": ocrText
    ]
    
    if let jsonData = try? JSONSerialization.data(withJSONObject: dict, options: []),
       let jsonString = String(data: jsonData, encoding: .utf8) {
        print(jsonString)
    }
} catch {
    print("{\"error\": \"\(error.localizedDescription)\"}")
}
