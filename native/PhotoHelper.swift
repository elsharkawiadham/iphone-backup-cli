import Foundation
import AppKit
import ImageCaptureCore
import CryptoKit

guard CommandLine.arguments.count == 2 else {
    print("Usage: PhotoHelper <destination-directory>")
    exit(2)
}

class Detector: NSObject, ICDeviceBrowserDelegate, ICCameraDeviceDelegate {
    var camera: ICCameraDevice?
    var retryCount = 0

    func deviceBrowser(_ browser: ICDeviceBrowser,
                       didAdd device: ICDevice,
                       moreComing: Bool) {
        guard let cam = device as? ICCameraDevice,
              camera == nil else { return }

        camera = cam
        cam.delegate = self
        print("iPhone detected. Requesting media session...")
        cam.requestOpenSession()
    }

    func deviceBrowser(_ browser: ICDeviceBrowser,
                       didRemove device: ICDevice,
                       moreGoing: Bool) {}

    func device(_ device: ICDevice,
                didOpenSessionWithError error: Error?) {
        if let error = error {
            let detail = error as NSError
            print("Session error:", detail.domain, detail.code,
                  detail.localizedDescription)

            if retryCount < 10 &&
               detail.localizedDescription.localizedCaseInsensitiveContains("unlock") {
                retryCount += 1
                print("Retrying session:", retryCount, "of 10")

                DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                    if let camera = self.camera {
                        print("Retry check: hasOpenSession =", camera.hasOpenSession)
                        if !camera.hasOpenSession {
                            print("Sending retry request")
                            camera.requestOpenSession()
                        } else {
                            print("Retry skipped: session already reported open")
                        }
                    }
                }
            } else {
                print("SESSION FAILED: No further retries")
            }
        } else {
            print("SUCCESS: Media session opened")
        }
    }

    func device(_ device: ICDevice,
                didCloseSessionWithError error: Error?) {}

    func didRemove(_ device: ICDevice) {}

    func deviceDidBecomeReady(withCompleteContentCatalog device: ICCameraDevice) {
        print("SUCCESS: Media catalog ready")
        print("Media file count:", device.mediaFiles?.count ?? 0)
        print("Session open:", device.hasOpenSession)

        guard let file = device.mediaFiles?
            .compactMap({ $0 as? ICCameraFile })
            .first(where: {
                $0.fileSize > 0 && $0.fileSize <= 8_388_608
            }) else {
            print("No suitable media file available")
            return
        }

        print("Requesting one complete small media file...")
        device.requestReadData(
            from: file,
            atOffset: 0,
            length: off_t(file.fileSize),
            readDelegate: self,
            didReadDataSelector: #selector(
                Detector.didReadData(_:fromFile:error:contextInfo:)
            ),
            contextInfo: nil
        )
    }

    @objc func didReadData(
        _ data: Data,
        fromFile file: ICCameraFile,
        error: Error?,
        contextInfo: UnsafeMutableRawPointer?
    ) {
        if let error = error {
            print("MEDIA READ ERROR:", error.localizedDescription)
        } else {
            guard Int64(data.count) == Int64(file.fileSize) else {
                print("FAILED: Received size does not match expected size")
                return
            }

            let folder = URL(
                fileURLWithPath: CommandLine.arguments[1],
                isDirectory: true
            )

            do {
                try FileManager.default.createDirectory(
                    at: folder,
                    withIntermediateDirectories: true
                )

                let destination = folder.appendingPathComponent(
                    "sample-\(UUID().uuidString).bin"
                )

                try data.write(to: destination, options: .atomic)
                let saved = try Data(contentsOf: destination)

                let verified = SHA256.hash(data: data) == SHA256.hash(data: saved)

                print("Bytes transferred:", data.count)
                print("SHA-256 verification:", verified ? "PASS" : "FAIL")
                print("Saved test file:", destination.path)
            } catch {
                print("FILE SAVE ERROR:", error.localizedDescription)
            }
        }
    }

    func cameraDevice(_ camera: ICCameraDevice, didAdd items: [ICCameraItem]) {}
    func cameraDevice(_ camera: ICCameraDevice, didRemove items: [ICCameraItem]) {}
    func cameraDevice(_ camera: ICCameraDevice, didRenameItems items: [ICCameraItem]) {}
    func cameraDevice(_ camera: ICCameraDevice, didReceiveMetadata metadata: [AnyHashable: Any]?, for item: ICCameraItem, error: Error?) {}
    func cameraDevice(_ camera: ICCameraDevice, didReceiveThumbnail thumbnail: CGImage?, for item: ICCameraItem, error: Error?) {}
    func cameraDeviceDidChangeCapability(_ camera: ICCameraDevice) {}
    func cameraDevice(_ camera: ICCameraDevice, didReceivePTPEvent eventData: Data) {}
    func cameraDeviceDidRemoveAccessRestriction(_ device: ICDevice) {}
    func cameraDeviceDidEnableAccessRestriction(_ device: ICDevice) {}
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)

let detector = Detector()
let browser = ICDeviceBrowser()
browser.delegate = detector
browser.browsedDeviceTypeMask = .camera

print("PhotoHelper starting...")
browser.start()

RunLoop.current.run(until: Date().addingTimeInterval(60))

if let camera = detector.camera, camera.hasOpenSession {
    camera.requestCloseSession()
}
browser.stop()
print("PhotoHelper finished")
