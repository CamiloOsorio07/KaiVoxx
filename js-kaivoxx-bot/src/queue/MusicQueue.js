class MusicQueue {
  constructor(limit = 500) {
    this._queue = [];
    this.limit = limit;
  }

  enqueue(item) {
    if (this._queue.length >= this.limit) return false;
    this._queue.push(item);
    return true;
  }

  dequeue() {
    return this._queue.length ? this._queue.shift() : null;
  }

  clear() {
    this._queue = [];
  }

  listTitles() {
    return this._queue.map((s) => s.title);
  }

  get length() {
    return this._queue.length;
  }

  [Symbol.iterator]() {
    return this._queue[Symbol.iterator]();
  }
}

module.exports = { MusicQueue };

