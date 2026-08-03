(function createPageResourceManager(global) {
  "use strict";

  class PageResources {
    constructor() {
      this.disposed = false;
      this.intervals = new Set();
      this.timeouts = new Set();
      this.listeners = new Set();
      this.controllers = new Set();
      this.lifecycleController = new AbortController();
    }

    get signal() {
      return this.lifecycleController.signal;
    }

    listen(target, type, listener, options) {
      if (this.disposed || !target) return listener;
      target.addEventListener(type, listener, options);
      this.listeners.add({ target, type, listener, options });
      return listener;
    }

    setInterval(callback, delay, ...args) {
      if (this.disposed) return null;
      const id = global.setInterval(callback, delay, ...args);
      this.intervals.add(id);
      return id;
    }

    setTimeout(callback, delay, ...args) {
      if (this.disposed) return null;
      let id = null;
      id = global.setTimeout(() => {
        this.timeouts.delete(id);
        callback(...args);
      }, delay);
      this.timeouts.add(id);
      return id;
    }

    createAbortController() {
      const controller = new AbortController();
      if (this.disposed) controller.abort();
      else this.controllers.add(controller);
      return controller;
    }

    cleanup() {
      if (this.disposed) return;
      this.disposed = true;
      this.intervals.forEach(id => global.clearInterval(id));
      this.timeouts.forEach(id => global.clearTimeout(id));
      this.listeners.forEach(({ target, type, listener, options }) => {
        target.removeEventListener(type, listener, options);
      });
      this.controllers.forEach(controller => controller.abort());
      this.lifecycleController.abort();
      this.intervals.clear();
      this.timeouts.clear();
      this.listeners.clear();
      this.controllers.clear();
    }
  }

  global.KOLConnectPageResources = Object.freeze({
    create() {
      return new PageResources();
    },
  });
})(window);
