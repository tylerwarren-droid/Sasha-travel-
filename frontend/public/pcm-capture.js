class PcmCapture extends AudioWorkletProcessor {
  process(inputs) {
    if (inputs[0][0]) this.port.postMessage(inputs[0][0].slice(0));
    return true;
  }
}
registerProcessor("pcm-capture", PcmCapture);
