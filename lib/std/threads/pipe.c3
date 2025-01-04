module std::io;

import std::thread;

struct Pipe
{
	PipeReader *r; 
	PipeWriter *w;
}

<*
 Pipe implements a synchronous in-memory pipe. It provides PipeReader and
 PipeWriter to connect code which expects an OutStream with one that
 expects an InStream.
 
 Each write to the PipeWriter will block until all data has been consumed by
 the PipeReader.
*>
fn void! Pipe.new(&self, Allocator allocator = allocator::heap())
{
	PipeImpl *pipe = allocator::new(allocator, PipeImpl).init(allocator)!;

	PipeReader *pr = allocator::new(allocator, PipeReader);
	pr.pipe = pipe;

	PipeWriter *pw = allocator::new(allocator, PipeWriter);
	pw.r = pr;

	*self = { pr, pw, };
}

fn void! Pipe.free(&self)
{
	if (!self.r) return;
	PipeImpl *pipe = self.r.pipe;
	if (!pipe) return;

	Allocator allocator = pipe.allocator;
	allocator::free(allocator, pipe);
	allocator::free(allocator, self.r);
	allocator::free(allocator, self.w);
	*self = {};
}

struct PipeReader (InStream)
{
	inline PipeImpl *pipe;
}

fn usz! PipeReader.read(&self, char[] bytes) @dynamic
{
	return self.pipe.read(bytes);
}

fn char! PipeReader.read_byte(&self) @dynamic
{
	return self.pipe.read_byte();
}

fn void! PipeReader.close(&self) @dynamic
{
	self.pipe.close()!;
}

struct PipeWriter (OutStream)
{
	inline PipeReader *r;
}

fn usz! PipeWriter.write(&self, char[] bytes) @dynamic
{
	return self.r.pipe.write(bytes);
}

fn void! PipeWriter.write_byte(&self, char c) @dynamic
{
	return self.r.pipe.write_byte(c);
}

fn void! PipeWriter.close(&self) @dynamic
{
	self.r.pipe.close()!;
}

struct PipeImpl (InStream, OutStream) @private
{
	Allocator allocator;
	ByteBuffer buf;

	Mutex mu;
	ConditionVariable wr;
	ConditionVariable rd;

	bool closed;
}

fn PipeImpl*! PipeImpl.init(&self, Allocator allocator)
{
	self.allocator = allocator;
	self.buf.new_init(256, 64, allocator)!;
	self.wr.init()!;
	self.rd.init()!;
	self.mu.init()!;
	return self;
}

fn void! PipeImpl.destroy(&self) @dynamic
{
	self.buf.free();
	self.wr.destroy()!;
	self.rd.destroy()!;
	self.mu.destroy()!;
	*self = {};
}

fn void! PipeImpl.close(&self) @dynamic
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
fn usz! PipeImpl.read(&self, char[] bytes) @dynamic
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

fn usz! PipeImpl.write(&self, char[] bytes) @dynamic
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

fn char! PipeImpl.read_byte(&self) @dynamic
{
	unsupported();
}

fn void! PipeImpl.write_byte(&self, char c) @dynamic
{
	unsupported();
}

