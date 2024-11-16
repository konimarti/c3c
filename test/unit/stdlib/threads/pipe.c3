module std::thread @test;

import std::io;

fn void! test_pipe()
{
	Pipe p; 
	p.init(allocator::temp())!;

	Thread tw;
	tw.create(fn int(void* arg) { 
		sleep_ms(1000);

		Pipe *p = arg;

		p.w.write("hello")!!;
		// sleep_ms(1000);

		p.w.write("--")!!;
		// sleep_ms(1000);

		p.w.write("world")!!;

		p.w.close()!!;
		return 0;
	}, &p)!;

	Thread tr;
	tr.create(fn int(void* arg) {
		sleep_ms(100);
		Pipe *p = arg;
		char[8]buf;

		for LOOP: (int i = 0; i < 5; i++)
		{
			usz! n = p.r.read(&buf);
			if (catch err = n)
			{
				if (err == IoError.EOF) break LOOP;
				return 1;
			}
			io::printfn("read: '%s'", (String)buf[:n]);
			sleep_ms(1000);
		}
		return 0;
	}, &p)!;

	tw.join()!;
	tr.join()!;
}

