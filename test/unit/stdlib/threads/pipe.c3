module std::thread @test;

import std::io;

fn void! test_pipe()
{
	Pipe p; 
	p.new_init(allocator::temp())!;
	// sleep_ms(100);

	Thread tw;
	tw.create(fn int(void* arg) { 
		Pipe *p = arg;
		p.write("hello")!!;
		p.write("--")!!;
		p.write("world")!!;
		sleep_ms(1000);
		p.close()!!;
		return 0;
	}, &p)!;

	Thread tw2;
	tw2.create(fn int(void* arg) { 
		Pipe *p = arg;
		p.write("hello")!!;
		p.write("--")!!;
		p.write("world")!!;
		sleep_ms(1000);
		p.close()!!;
		return 0;
	}, &p)!;

	Thread tr;
	tr.create(fn int(void* arg) {
		Pipe *p = arg;
		char[2]buf;
		usz i;
		while (try n = p.read(&buf)) 
		{
			io::printfn("[1] %d read: '%s'", ++i, (String)buf[:n]);
			sleep_ms(100);
		}
		return 0;
	}, &p)!;

	// Thread tr2;
	// tr2.create(fn int(void* arg) { 
	// 	Pipe *p = arg;
	// 	char[2] buf;
	// 	usz i;
	// 	while (try n = p.read(&buf)) 
	// 	{
	// 		io::printfn("[2] %d read: '%s'", ++i, (String)buf[:n]);
	// 		sleep_ms(100);
	// 	}
	// 	return 0;
	// }, &p)!;


	tw.join()!;
	tw2.join()!;

	tr.join()!;
	// tr2.join()!;

	p.free()!;
}

