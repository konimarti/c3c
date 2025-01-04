module std::io;

import std::thread;

struct Pipe (InStream, OutStream)
{
	Allocator allocator;
	ByteBuffer buf;

	Mutex mu;
	ConditionVariable wr;
	ConditionVariable rd;

	bool closed;
}

<*
 Pipe implements a synchronous in-memory pipe. It provides PipeReader and
 PipeWriter to connect code which expects an OutStream with one that
 expects an InStream.
 
 Each write to the PipeWriter will block until all data has been consumed by
 the PipeReader.
*>
fn Pipe*! Pipe.new_init(&self, Allocator allocator = allocator::heap())
{
	self.allocator = allocator;
	self.buf.new_init(256, 64, allocator)!;
	self.wr.init()!;
	self.rd.init()!;
	self.mu.init()!;
	return self;
}

fn void! Pipe.free(&self) @dynamic
{
	if (!self.closed) (void)self.close();
	(void)self.wr.destroy();
	(void)self.rd.destroy();
	(void)self.mu.destroy();
	self.buf.free();
	*self = {};
}

fn void! Pipe.close(&self) @dynamic
{
	self.mu.lock()!;
	defer (void)self.mu.unlock();

	self.closed = true;

	self.wr.signal()!;
	self.rd.signal()!;
}

<*
@param [&inout] self
*>
fn usz! Pipe.read(&self, char[] bytes) @dynamic
{
	self.mu.lock()!;
	defer (void)self.mu.unlock();

	while (self.buf.available()! == 0 && !self.closed)
	{
		self.rd.wait(&self.mu)!; // wait for write to read data
	}

	if (self.closed && !self.buf.available()!)
	{
		return IoError.EOF?;
	}

	usz! n =  self.buf.read(bytes);

	self.wr.signal()!; // signal write that it can process

	return n;
}

fn usz! Pipe.write(&self, char[] bytes) @dynamic
{
	self.mu.lock()!;
	defer (void)self.mu.unlock();

	while (self.buf.available()!)
	{
		self.wr.wait(&self.mu)!; // wait until read is done for existing data
	}

	if (self.closed)
	{
		return IoError.EOF?;
	}

	usz! n = self.buf.write(bytes);

	self.rd.signal()!;

	return n;
}

fn char! Pipe.read_byte(&self) @dynamic
{
	unsupported();
}

fn void! Pipe.write_byte(&self, char c) @dynamic
{
	unsupported();
}

