/*
 * AIM bridge probe for an instrumented/test copy of Xianyu.
 *
 * The script keeps the App-specific Objective-C objects inside the App
 * process.  The host sees only versioned JSON events/results.  It starts in a
 * read-only mode: listener registration and native sending are opt-in through
 * rpc.exports.configure({registerListener:true, invokeEnabled:true}).
 */

'use strict';

const NULL = ptr('0');
const DEFAULT_CONFIG = {
  accountId: 'ACCOUNT_ID',
  captureText: false,
  registerListener: false,
  invokeEnabled: false,
  contentTypeText: 1,
};

const config = Object.assign({}, DEFAULT_CONFIG);
const state = {
  service: null,
  listener: null,
  listenerClass: null,
  hooks: [],
  blocks: {},
  startedAtMs: Date.now(),
};

function nowMs() {
  return Date.now();
}

function emit(kind, frame) {
  send({kind: kind, frame: frame});
}

function observation(kind, data) {
  send({
    kind: 'native.observation',
    observation: Object.assign({kind: kind, observedAtMs: nowMs()}, data || {}),
  });
}

function status(stateName, extra) {
  emit('native.event', Object.assign({
    event: 'transport.status',
    account_id: String(config.accountId),
    state: stateName,
    last_heartbeat_ms: nowMs(),
    reconnect_count: 0,
  }, extra || {}));
}

function asObjC(value) {
  if (value === null || value === undefined) return null;
  try {
    if (value.isNull && value.isNull()) return null;
  } catch (_) {
    // Keep trying; some Frida wrappers do not expose isNull().
  }
  try {
    if (value.$className) return value;
  } catch (_) {
    // Not an existing ObjC wrapper.
  }
  try {
    return new ObjC.Object(value);
  } catch (_) {
    return null;
  }
}

function pointerString(value) {
  try {
    if (!value) return null;
    if (value.handle) return value.handle.toString();
    return value.toString();
  } catch (_) {
    return null;
  }
}

function selectorToJs(selector) {
  return selector.replace(/:/g, '_');
}

function getSelectorMethod(object, selector) {
  if (!object) return null;
  const name = selectorToJs(selector);
  try {
    if (typeof object[name] === 'function') return object[name];
  } catch (_) {
    // Continue with a direct selector lookup below.
  }
  try {
    const method = object[selector];
    if (typeof method === 'function') return method;
  } catch (_) {
    // No method on this object/version.
  }
  return null;
}

function callSelector(object, selector, args) {
  const method = getSelectorMethod(object, selector);
  if (!method) return null;
  try {
    return method.apply(object, args || []);
  } catch (_) {
    return null;
  }
}

function prop(object, names) {
  const target = asObjC(object);
  if (!target) return null;
  for (const name of names) {
    const value = callSelector(target, name, []);
    if (value !== null && value !== undefined) return value;
  }
  return null;
}

function stringValue(value, allowText) {
  const target = asObjC(value);
  if (!target) return null;
  try {
    const className = String(target.$className || '');
    if (className.indexOf('String') >= 0 || className.indexOf('Number') >= 0) {
      const text = target.toString();
      return allowText ? text : '<redacted>';
    }
    if (typeof target.toString === 'function') {
      const text = target.toString();
      return allowText ? text : '<redacted>';
    }
  } catch (_) {
    // Keep metadata-only decoding alive if an object has a custom formatter.
  }
  return null;
}

function identifierValue(object, names) {
  const value = prop(object, names);
  const text = stringValue(value, true);
  return text || null;
}

function describeObject(value, includeText) {
  const target = asObjC(value);
  if (!target) return null;
  const result = {
    className: String(target.$className || 'unknown'),
    pointer: pointerString(target),
  };
  if (includeText) {
    const text = stringValue(target, true);
    if (text !== null) result.text = text;
  }
  return result;
}

function findService() {
  if (state.service) return state.service;
  if (!ObjC.available || !ObjC.classes.AIMPubMsgService) return null;
  try {
    ObjC.choose(ObjC.classes.AIMPubMsgService, {
      onMatch(instance) {
        if (!state.service) state.service = instance;
      },
      onComplete() {},
    });
  } catch (_) {
    // An instance may not exist until the App finishes login/bootstrap.
  }
  return state.service;
}

function methodFor(className, selector) {
  if (!ObjC.available || !ObjC.classes[className]) return null;
  const cls = ObjC.classes[className];
  const candidates = ['- ' + selector, selector, '+ ' + selector];
  for (const candidate of candidates) {
    try {
      if (cls[candidate]) return cls[candidate];
    } catch (_) {
      // Try the next Frida selector spelling.
    }
  }
  return null;
}

function methodDescription(className, selector) {
  const method = methodFor(className, selector);
  if (!method) return null;
  let argumentTypes = null;
  let returnType = null;
  try { argumentTypes = method.argumentTypes || null; } catch (_) {}
  try { returnType = method.returnType || null; } catch (_) {}
  return {
    className: className,
    selector: selector,
    implementation: method.implementation ? method.implementation.toString() : null,
    argumentTypes: argumentTypes,
    returnType: returnType,
  };
}

function hookObjC(className, selector, callbacks) {
  const method = methodFor(className, selector);
  if (!method || !method.implementation) {
    observation('selector.missing', {className: className, selector: selector});
    return false;
  }
  try {
    const handle = Interceptor.attach(method.implementation, callbacks || {});
    state.hooks.push(handle);
    return true;
  } catch (error) {
    observation('selector.hook_error', {
      className: className,
      selector: selector,
      error: String(error),
    });
    return false;
  }
}

function messageSummary(message, includeText) {
  const target = asObjC(message);
  if (!target) return null;
  const content = prop(target, ['content', 'msgContent', 'messageContent']);
  const textContent = content ? prop(content, ['textContent']) : null;
  const text = includeText && textContent ? identifierValue(textContent, ['text']) : null;
  const sender = identifierValue(target, ['sender', 'senderUid', 'senderId', 'fromUid']);
  const receiver = identifierValue(target, ['receiver', 'receiverUid', 'receiverId', 'toUid']);
  const summary = {
    className: String(target.$className || 'unknown'),
    pointer: pointerString(target),
    messageId: identifierValue(target, ['mid', 'messageId', 'messageID', 'msgId', 'localId']),
    appCid: identifierValue(target, ['appCid', 'appCID', 'conversationId', 'cid']),
    sid: identifierValue(target, ['sid', 'sessionId', 'sessionID']),
    sender: sender,
    receiver: receiver,
    contentType: identifierValue(content, ['contentType', 'type']),
  };
  if (text !== null) summary.text = text;
  return summary;
}

function normaliseMessage(message) {
  const summary = messageSummary(message, config.captureText);
  if (!summary || !summary.messageId) return null;
  const own = String(config.accountId);
  const direction = summary.sender === own ? 'out' : 'in';
  const peer = direction === 'out' ? summary.receiver : summary.sender;
  const frame = {
    event: 'message.received',
    account_id: own,
    message_id: String(summary.messageId),
    sid: summary.sid,
    app_cid: summary.appCid,
    peer_uid: peer,
    direction: direction,
    content_type: summary.text !== undefined && summary.text !== null ? 'text' : 'unknown',
    created_at_ms: nowMs(),
  };
  if (summary.text !== undefined && summary.text !== null) frame.text = summary.text;
  return frame;
}

function onAddedMessages(messages) {
  const collection = asObjC(messages);
  if (!collection) {
    observation('message.callback.empty');
    return;
  }
  let count = 1;
  let isCollection = false;
  try {
    if (typeof collection.count === 'function') {
      count = Math.min(Number(collection.count()), 100);
      isCollection = typeof collection.objectAtIndex_ === 'function';
    }
  } catch (_) {}
  for (let index = 0; index < count; index += 1) {
    let message = collection;
    if (isCollection) message = callSelector(collection, 'objectAtIndex:', [index]);
    const frame = normaliseMessage(message);
    if (frame) emit('native.event', frame);
    else observation('message.decode_miss', {index: index, object: describeObject(message, false)});
  }
}

function registerListener() {
  if (state.listener) return true;
  if (!ObjC.available || !ObjC.protocols.AIMPubMsgListener) {
    observation('listener.protocol_missing');
    return false;
  }
  const methodBody = function(messages) { onAddedMessages(messages); };
  let klass = null;
  try {
    klass = ObjC.registerClass({
      name: 'XianYuAIMBridgeListener' + Process.id,
      protocols: [ObjC.protocols.AIMPubMsgListener],
      methods: {'- onAddedMessages:': methodBody},
    });
  } catch (_) {
    try {
      klass = ObjC.registerClass({
        name: 'XianYuAIMBridgeListener' + Process.id,
        protocols: [ObjC.protocols.AIMPubMsgListener],
        methods: {'onAddedMessages:': methodBody},
      });
    } catch (error) {
      observation('listener.register_error', {error: String(error)});
      return false;
    }
  }
  try {
    state.listenerClass = klass;
    state.listener = klass.alloc().init();
    const service = findService();
    if (!service) {
      observation('listener.service_missing');
      return false;
    }
    const result = callSelector(service, 'addMsgListener:', [state.listener]);
    observation('listener.registered', {
      service: pointerString(service),
      listener: pointerString(state.listener),
      result: result === null ? null : String(result),
    });
    status('connected');
    return true;
  } catch (error) {
    observation('listener.install_error', {error: String(error)});
    return false;
  }
}

function hookAIMCalls() {
  hookObjC('AIMPubMsgService', 'initWithCpp:', {
    onLeave(retval) {
      const object = asObjC(retval);
      if (object) {
        state.service = object;
        observation('service.instance', {pointer: pointerString(object)});
        if (config.registerListener) registerListener();
      }
    },
  });
  hookObjC('AIMPubMsgService', 'addMsgListener:', {
    onEnter(args) {
      state.service = asObjC(args[0]) || state.service;
      observation('listener.add_call', {
        service: pointerString(args[0]),
        listener: pointerString(args[2]),
      });
    },
  });
  for (const selector of [
    'sendMessageWithBlock:onProgress:onSuccess:onFailure:userData:',
    'replyMessageWithBlock:onProgress:onSuccess:onFailure:userData:',
  ]) {
    hookObjC('AIMPubMsgService', selector, {
      onEnter(args) {
        const messageObject = asObjC(args[2]);
        observation('message.send_call', {
          selector: selector,
          service: pointerString(args[0]),
          message: messageSummary(messageObject, config.captureText),
        });
      },
    });
  }
  hookObjC('AIMPubMsgHookPreSendMsgListener', 'onSuccess:saveToLocal:', {
    onEnter(args) {
      observation('message.native_success', {
        message: messageSummary(asObjC(args[2]), false),
        saveToLocal: args[3].toInt32(),
      });
    },
  });
  hookObjC('AIMPubMsgHookPreSendMsgListener', 'onFailure:', {
    onEnter(args) {
      observation('message.native_failure', {
        error: describeObject(args[2], false),
      });
    },
  });
}

function emptyDictionary() {
  try { return ObjC.classes.NSDictionary.dictionary(); } catch (_) { return NULL; }
}

function makeString(value) {
  return ObjC.classes.NSString.stringWithString_(String(value));
}

function makeReceivers(peerUid) {
  if (!peerUid) return ObjC.classes.NSArray.array();
  return ObjC.classes.NSArray.arrayWithObject_(makeString(peerUid));
}

function makeTextContent(text) {
  const klass = ObjC.classes.AIMPubMsgTextContent;
  if (!klass) throw new Error('AIMPubMsgTextContent is not loaded');
  return klass.alloc().initWithText_encryptedText_extension_(
    makeString(text), NULL, emptyDictionary()
  );
}

function makeContent(text) {
  const klass = ObjC.classes.AIMPubMsgContent;
  if (!klass) throw new Error('AIMPubMsgContent is not loaded');
  const textContent = makeTextContent(text);
  return klass.alloc().initWithContentType_textContent_imageContent_audioContent_videoContent_geoContent_customContent_structContent_fileContent_replyContent_combineForwardContent_(
    Number(config.contentTypeText),
    textContent,
    NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
  );
}

function resultMessageId(message) {
  return identifierValue(message, ['mid', 'messageId', 'messageID', 'msgId', 'localId']);
}

function errorCode(errorObject) {
  const code = identifierValue(errorObject, ['code', 'errorCode', 'error_code']);
  return code || 'AIM_ERROR';
}

function invokeSend(frame) {
  const service = findService();
  if (!service) throw new Error('AIMPubMsgService instance not found');
  const appCid = makeString(frame.app_cid || frame.sid || '');
  const receivers = makeReceivers(frame.peer_uid);
  const extension = emptyDictionary();
  const localExtension = emptyDictionary();
  const callbackCtx = emptyDictionary();
  const requestId = String(frame.request_id);
  const content = makeContent(frame.text);

  let requestObject;
  let selector;
  if (frame.reply_to_mid) {
    const klass = ObjC.classes.AIMPubMsgSendReplyMessage;
    requestObject = klass.alloc().initWithAppCid_referenceMid_replyContent_receivers_extension_localExtension_callbackCtx_(
      appCid,
      makeString(frame.reply_to_mid),
      content,
      receivers,
      extension,
      localExtension,
      callbackCtx
    );
    selector = 'replyMessageWithBlock:onProgress:onSuccess:onFailure:userData:';
  } else {
    const klass = ObjC.classes.AIMPubMsgSendMessage;
    requestObject = klass.alloc().initWithAppCid_content_receivers_extension_localExtension_callbackCtx_customLocalid_(
      appCid,
      content,
      receivers,
      extension,
      localExtension,
      callbackCtx,
      makeString(requestId)
    );
    selector = 'sendMessageWithBlock:onProgress:onSuccess:onFailure:userData:';
  }

  const progress = new ObjC.Block({
    retType: 'void',
    argTypes: ['double'],
    implementation(progressValue) {
      observation('message.progress', {requestId: requestId, progress: Number(progressValue)});
    },
  });
  const success = new ObjC.Block({
    retType: 'void',
    argTypes: ['object'],
    implementation(message) {
      const event = {
        event: 'message.send.result',
        account_id: String(config.accountId),
        request_id: requestId,
        status: 'sent',
        message_id: resultMessageId(asObjC(message)),
        error_code: null,
        error_message: null,
        observed_at_ms: nowMs(),
      };
      emit('native.event', event);
      delete state.blocks[requestId];
    },
  });
  const failure = new ObjC.Block({
    retType: 'void',
    argTypes: ['object'],
    implementation(errorObject) {
      emit('native.event', {
        event: 'message.send.result',
        account_id: String(config.accountId),
        request_id: requestId,
        status: 'failed',
        message_id: null,
        error_code: errorCode(asObjC(errorObject)),
        error_message: 'AIM send callback reported failure',
        observed_at_ms: nowMs(),
      });
      delete state.blocks[requestId];
    },
  });
  state.blocks[requestId] = {progress: progress, success: success, failure: failure};
  const method = getSelectorMethod(service, selector);
  if (!method) throw new Error('AIM send selector is not available');
  method.call(service, requestObject, progress, success, failure, NULL);
}

function handleCommand(frame) {
  if (!frame || typeof frame !== 'object') return;
  if (frame.action === 'ping') {
    status('connected');
    return;
  }
  if (frame.action !== 'send_text' && frame.action !== 'reply_text') return;
  const requestId = String(frame.request_id || 'REQ');
  if (!config.invokeEnabled) {
    emit('native.event', {
      event: 'message.send.result',
      account_id: String(config.accountId),
      request_id: requestId,
      status: 'failed',
      message_id: null,
      error_code: 'NATIVE_INVOKE_DISABLED',
      error_message: 'native invocation is disabled in the probe',
      observed_at_ms: nowMs(),
    });
    return;
  }
  try {
    invokeSend(frame);
  } catch (error) {
    emit('native.event', {
      event: 'message.send.result',
      account_id: String(config.accountId),
      request_id: requestId,
      status: 'failed',
      message_id: null,
      error_code: 'NATIVE_INVOKE_ERROR',
      error_message: String(error),
      observed_at_ms: nowMs(),
    });
  }
}

function receiveCommands() {
  recv('native.command', function(message) {
    try {
      handleCommand(message && message.payload ? message.payload : message);
    } finally {
      receiveCommands();
    }
  });
}

function discover() {
  const result = [];
  if (!ObjC.available) return result;
  for (const className of [
    'AIMPubMsgService',
    'AIMPubMsgTextContent',
    'AIMPubMsgContent',
    'AIMPubMsgSendMessage',
    'AIMPubMsgSendReplyMessage',
    'AIMPubMsgHookPreSendMsgListener',
  ]) {
    for (const selector of [
      'initWithCpp:',
      'addMsgListener:',
      'sendMessageWithBlock:onProgress:onSuccess:onFailure:userData:',
      'replyMessageWithBlock:onProgress:onSuccess:onFailure:userData:',
      'initWithText:encryptedText:extension:',
      'initWithContentType:textContent:imageContent:audioContent:videoContent:geoContent:customContent:structContent:fileContent:replyContent:combineForwardContent:',
      'initWithAppCid:content:receivers:extension:localExtension:callbackCtx:customLocalid:',
      'initWithAppCid:referenceMid:replyContent:receivers:extension:localExtension:callbackCtx:',
      'onAddedMessages:',
      'onSuccess:saveToLocal:',
      'onFailure:',
    ]) {
      const description = methodDescription(className, selector);
      if (description) result.push(description);
    }
  }
  return result;
}

rpc.exports = {
  configure(patch) {
    Object.assign(config, patch || {});
    if (config.registerListener) registerListener();
    return Object.assign({}, config, {
      service: pointerString(state.service),
      listener: pointerString(state.listener),
    });
  },
  discover() {
    return discover();
  },
  state() {
    return {
      config: Object.assign({}, config),
      service: pointerString(state.service),
      listener: pointerString(state.listener),
      hookCount: state.hooks.length,
      uptimeMs: nowMs() - state.startedAtMs,
    };
  },
};

setImmediate(function() {
  if (!ObjC.available) {
    observation('objc.unavailable');
    return;
  }
  hookAIMCalls();
  status('app_ready');
  receiveCommands();
  if (config.registerListener) registerListener();
});
