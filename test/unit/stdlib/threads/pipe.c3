module std::thread @test;

import std::io;

fn void! test_pipe()
{
	Pipe p; 
	p.new(allocator::temp())!;
	// sleep_ms(100);

	Thread tw;
	tw.create(fn int(void* arg) { 
		Pipe *p = arg;
		p.w.write("hello")!!;
		p.w.write("--")!!;
		p.w.write("world")!!;
		p.w.close()!!;
		return 0;
	}, &p)!;

	Thread tr;
	tr.create(fn int(void* arg) {
		Pipe *p = arg;
		char[2]buf;
		usz i;
		while (try n = p.r.read(&buf)) 
		{
			io::printfn("%d read: '%s'", ++i, (String)buf[:n]);
		}
		p.r.close()!!;
		return 0;
	}, &p)!;

	tw.join()!;
	tr.join()!;

	p.free()!;
}

