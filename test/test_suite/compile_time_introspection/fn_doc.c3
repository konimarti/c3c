<*
 Adds two numbers.

 @param a : "first"
 @return "the sum"
*>
fn int add(int a, int b = 1) => a + b;

fn int nodoc(int x) => x;

<* Only text. *>
fn void textonly() {}

fn void main()
{
	$assert $Typeof(&add)::doc == "Adds two numbers.";
	$assert $Typeof(&add)::return_doc == "the sum";
	$assert $Typeof(&nodoc)::doc == "";
	$assert $Typeof(&nodoc)::return_doc == "";
	$assert $Typeof(&textonly)::doc == "Only text.";
	$assert $Typeof(&textonly)::return_doc == "";
}
