/*
 * Frida discovery script for an instrumented/test copy of Xianyu.
 *
 * It only enumerates class methods and symbol names.  It intentionally does
 * not print cookies, access tokens, message bodies, or callback arguments.
 * After a manual send, use the printed IMP addresses to add a narrow hook for
 * the exact selector/version under test.
 */

'use strict';

const CLASS_RE = /AIM(PubMsgService|MsgService|MsgNotify)/i;
const SELECTOR_RE = /(send|reply|resend|message|notify|added)/i;
const SYMBOL_RE = /(AIMMsgServiceEx|AIMMsgNotify|AIMMsgListenerImpl|AIMMsgServiceHookImpl|SendMessage|ReplyMessage|NotifyAddedNewMsg|OnAddedMessages|PreReceiveMessage|PreSendMessage)/i;
// Set to true only in a disposable instrumented copy after confirming the
// process and ABI.  The default is metadata-only enumeration.
const HOOK_NATIVE = false;

function enumerateObjC() {
  if (!ObjC.available) {
    console.log('[native-im] Objective-C runtime is unavailable');
    return;
  }

  for (const className of Object.keys(ObjC.classes).sort()) {
    if (!CLASS_RE.test(className)) continue;
    const cls = ObjC.classes[className];
    console.log(`\n[objc] ${className}`);
    for (const rawSelector of (cls.$ownMethods || []).sort()) {
      if (!SELECTOR_RE.test(rawSelector)) continue;
      try {
        const method = cls[rawSelector];
        const imp = method && method.implementation;
        console.log(`  ${rawSelector} @ ${imp || '<none>'}`);
      } catch (error) {
        console.log(`  ${rawSelector} @ <error>`);
      }
    }
  }

  // Djinni exposes the listener as an Objective-C protocol.  Frida versions
  // differ in how protocol methods are surfaced, so print whichever view is
  // available before attempting addMsgListener:.
  try {
    const proto = ObjC.protocols.AIMPubMsgListener;
    if (proto) {
      console.log('\n[protocol] AIMPubMsgListener');
      for (const key of ['$methods', '$classMethods']) {
        if (Array.isArray(proto[key])) {
          console.log(`  ${key}: ${proto[key].join(', ')}`);
        }
      }
    }
  } catch (_) {
    // Metadata-only probe; protocol enumeration is optional.
  }
}

function enumerateNativeSymbols() {
  for (const module of Process.enumerateModules()) {
    let symbols;
    try {
      symbols = module.enumerateSymbols();
    } catch (_) {
      continue;
    }
    for (const symbol of symbols) {
      const name = symbol.name || '';
      if (!SYMBOL_RE.test(name)) continue;
      console.log(`[native] ${module.name}!${name} @ ${symbol.address}`);
    }
  }
}

function hookNativeCallbacks() {
  if (!HOOK_NATIVE) return;
  const wanted = /(AIMMsgListenerImpl.*OnAddedMessages|AIMMsgServiceHookImpl.*PreReceiveMessage|AIMMsgServiceHookImpl.*PreSendMessage)/i;
  const attached = new Set();
  for (const module of Process.enumerateModules()) {
    let symbols;
    try {
      symbols = module.enumerateSymbols();
    } catch (_) {
      continue;
    }
    for (const symbol of symbols) {
      if (!wanted.test(symbol.name || '') || attached.has(symbol.address.toString())) {
        continue;
      }
      attached.add(symbol.address.toString());
      Interceptor.attach(symbol.address, {
        onEnter(args) {
          // C++ std::vector<T> is passed by reference in x1 on arm64.  We log
          // only its pointer pair here; element decoding comes after ABI
          // confirmation and stays out of the first-pass probe.
          let begin = '<unreadable>';
          let end = '<unreadable>';
          try {
            begin = args[1].readPointer();
            end = args[1].add(Process.pointerSize).readPointer();
          } catch (_) {
            // Keep the callback alive if a different ABI is encountered.
          }
          console.log(`[callback] ${symbol.name} begin=${begin} end=${end}`);
        }
      });
    }
  }
}

/*
 * Narrow hook template.  Enable it only after the selector has been confirmed
 * from the enumeration above:
 *
 * const cls = ObjC.classes.AIMPubMsgService;
 * const method = cls['- sendMessageWithBlock:onProgress:onSuccess:onFailure:userData:'];
 * Interceptor.attach(method.implementation, {
 *   onEnter(args) {
 *     // args[2] is the AIM send-message object on this ABI.
 *     console.log('[send] AIMPubMsgService called');
 *   }
 * });
 */

setImmediate(() => {
  enumerateObjC();
  enumerateNativeSymbols();
  hookNativeCallbacks();
});
