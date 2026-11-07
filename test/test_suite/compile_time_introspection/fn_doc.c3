<*
 Adds two numbers.

 @param a : "first"
 @return "the sum"
*>
fn int add(int a, int b = 1) => a + b;

fn int nodoc(int x) => x;

<* Only text. *>
fn void textonly() {}

<*
 @param x : "only a param"
*>
fn void onlyparam(int x) {}

<*
 First line.
 Second line.
*>
fn void multiline() {}

struct Foo { int x; }

<*
 Method doc.
 @return "method result"
*>
fn int Foo.get(&self) => self.x;

alias Plain = fn int(int);

fn void main()
{
	$assert $Typeof(&add)::doc == "Adds two numbers.";
	$assert $Typeof(&add)::return_doc == "the sum";
	$assert $Typeof(&nodoc)::doc == "";
	$assert $Typeof(&nodoc)::return_doc == "";
	$assert $Typeof(&textonly)::doc == "Only text.";
	$assert $Typeof(&textonly)::return_doc == "";
	$assert $Typeof(&onlyparam)::doc == "";
	$assert $Typeof(&onlyparam)::return_doc == "";
	$assert $Typeof(&multiline)::doc == "First line.\nSecond line.";
	$assert $Typeof(&Foo.get)::doc == "Method doc.";
	$assert $Typeof(&Foo.get)::return_doc == "method result";
	$assert Plain::doc == "";
	$assert Plain::return_doc == "";
}
